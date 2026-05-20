"""
Long-term Memory System using Vector Database (ChromaDB)
Stores and retrieves memories using semantic search
"""
import hashlib
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from ..utils.config import get_config
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Memory:
    """Represents a single long-term memory entry"""
    id: str
    content: str
    memory_type: str  # "preference", "fact", "context", "learning"
    importance: str = "medium"  # "high", "medium", "low"
    source: str = "conversation"  # Where this memory came from
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


class LongTermMemory:
    """
    Long-term Memory with ChromaDB Vector Storage
    
    Features:
    - Semantic search for relevant memories
    - Memory importance scoring
    - Automatic memory extraction from conversations
    - Memory consolidation and cleanup
    
    Usage:
        memory = LongTermMemory()
        
        await memory.initialize()
        
        # Add memories
        memory.add_memory(
            content="User likes Python programming",
            memory_type="preference",
            importance="high",
        )
        
        # Search memories
        results = await memory.search("programming languages")
    """
    
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        """
        Initialize long-term memory system
        
        Args:
            persist_directory: Directory to store vector database
            collection_name: Name of the collection
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "ChromaDB is required for long-term memory. "
                "Install it with: pip install chromadb"
            )
        
        config = get_config().config.memory.long_term
        
        self.persist_directory = persist_directory or config.persist_directory
        self.collection_name = collection_name or config.collection_name
        self.embedding_model = config.embedding_model
        self.similarity_threshold = config.similarity_threshold
        self.max_results = config.max_results
        
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None
        self._initialized: bool = False
        
        logger.info(
            f"LongTermMemory initialized "
            f"(collection={self.collection_name}, "
            f"persist_dir={self.persist_directory})"
        )
    
    async def initialize(self) -> None:
        """Initialize the vector database connection"""
        try:
            # Create persist directory if not exists
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            
            # Initialize ChromaDB client
            self._client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                ),
            )
            
            # Get or create collection
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Agent long-term memories"},
            )
            
            self._initialized = True
            logger.info(
                f"Long-term memory initialized with "
                f"{self._collection.count()} existing memories"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize long-term memory: {e}")
            raise
    
    def _generate_id(self, content: str) -> str:
        """Generate unique ID for memory based on content hash"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def add_memory(
        self,
        content: str,
        memory_type: str = "context",
        importance: str = "medium",
        source: str = "conversation",
        metadata: Optional[Dict] = None,
    ) -> Memory:
        """
        Add a new memory to long-term storage
        
        Args:
            content: Memory content text
            memory_type: Type of memory (preference, fact, context, learning)
            importance: Importance level (high, medium, low)
            source: Source of this memory
            metadata: Additional metadata
            
        Returns:
            Created Memory object
        """
        if not self._initialized:
            await self.initialize()
        
        memory_id = self._generate_id(content)
        now = datetime.now()
        
        memory = Memory(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            source=source,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        
        # Store in ChromaDB
        self._collection.upsert(
            ids=[memory_id],
            documents=[content],
            metadatas=[memory.to_dict()],
        )
        
        logger.info(
            f"Added memory [{memory_id[:8]}]: "
            f"{content[:50]}... (type={memory_type}, importance={importance})"
        )
        
        return memory
    
    async def add_memories_batch(
        self,
        memories: List[Dict[str, Any]],
    ) -> List[Memory]:
        """
        Add multiple memories at once
        
        Args:
            memories: List of memory dictionaries
            
        Returns:
            List of created Memory objects
        """
        if not self._initialized:
            await self.initialize()
        
        created_memories = []
        ids = []
        documents = []
        metadatas = []
        
        for mem_data in memories:
            memory = Memory(
                id=self._generate_id(mem_data["content"]),
                content=mem_data["content"],
                memory_type=mem_data.get("memory_type", "context"),
                importance=mem_data.get("importance", "medium"),
                source=mem_data.get("source", "conversation"),
                metadata=mem_data.get("metadata", {}),
            )
            
            created_memories.append(memory)
            ids.append(memory.id)
            documents.append(memory.content)
            metadatas.append(memory.to_dict())
        
        # Batch upsert
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        
        logger.info(f"Batch added {len(memories)} memories")
        return created_memories
    
    async def search(
        self,
        query: str,
        n_results: Optional[int] = None,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Memory]:
        """
        Search for relevant memories using semantic similarity
        
        Args:
            query: Search query text
            n_results: Number of results to return
            filter_metadata: Metadata filters
            
        Returns:
            List of relevant Memory objects sorted by relevance
        """
        if not self._initialized:
            await self.initialize()
        
        n_results = n_results or self.max_results
        
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter_metadata,
                include=["documents", "metadatas", "distances"],
            )
            
            memories = []
            if results and results['documents']:
                for doc, meta, distance in zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0],
                ):
                    # Filter by similarity threshold
                    similarity_score = 1 - distance
                    
                    if similarity_score >= self.similarity_threshold:
                        memory = Memory(
                            id=meta['id'],
                            content=doc,
                            memory_type=meta['memory_type'],
                            importance=meta['importance'],
                            source=meta['source'],
                            created_at=datetime.fromisoformat(meta['created_at']),
                            updated_at=datetime.fromisoformat(meta['updated_at']),
                            metadata=meta.get('metadata', {}),
                        )
                        memory._similarity_score = similarity_score
                        memories.append(memory)
                
                logger.debug(
                    f"Search '{query[:30]}...' returned "
                    f"{len(memories)} memories (threshold={self.similarity_threshold})"
                )
            
            return memories
            
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []
    
    async def get_by_id(self, memory_id: str) -> Optional[Memory]:
        """
        Retrieve a specific memory by ID
        
        Args:
            memory_id: Unique memory identifier
            
        Returns:
            Memory object or None if not found
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            results = self._collection.get(
                ids=[memory_id],
                include=["documents", "metadatas"],
            )
            
            if results and results['documents']:
                meta = results['metadatas'][0]
                return Memory(
                    id=meta['id'],
                    content=results['documents'][0],
                    memory_type=meta['memory_type'],
                    importance=meta['importance'],
                    source=meta['source'],
                    created_at=datetime.fromisoformat(meta['created_at']),
                    updated_at=datetime.fromisoformat(meta['updated_at']),
                    metadata=meta.get('metadata', {}),
                )
            return None
            
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
            return None
    
    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        **kwargs,
    ) -> Optional[Memory]:
        """
        Update an existing memory
        
        Args:
            memory_id: ID of memory to update
            content: New content (optional)
            **kwargs: Other fields to update
            
        Returns:
            Updated Memory object or None
        """
        if not self._initialized:
            await self.initialize()
        
        existing = await self.get_by_id(memory_id)
        if not existing:
            logger.warning(f"Memory {memory_id} not found for update")
            return None
        
        # Update fields
        if content:
            existing.content = content
        for key, value in kwargs.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
        existing.updated_at = datetime.now()
        
        # Re-store in ChromaDB
        self._collection.update(
            ids=[memory_id],
            documents=[existing.content],
            metadatas=[existing.to_dict()],
        )
        
        logger.info(f"Updated memory {memory_id[:8]}")
        return existing
    
    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory by ID
        
        Args:
            memory_id: ID of memory to delete
            
        Returns:
            True if deleted successfully
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            self._collection.delete(ids=[memory_id])
            logger.info(f"Deleted memory {memory_id[:8]}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False
    
    async def get_all_memories(
        self,
        memory_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Memory]:
        """
        Get all memories, optionally filtered by type
        
        Args:
            memory_type: Filter by memory type
            limit: Maximum number of memories to return
            
        Returns:
            List of Memory objects
        """
        if not self._initialized:
            await self.initialize()
        
        filter_meta = {"memory_type": memory_type} if memory_type else None
        
        try:
            results = self._collection.get(
                where=filter_meta,
                limit=limit,
                include=["documents", "metadatas"],
            )
            
            memories = []
            if results and results['documents']:
                for doc, meta in zip(results['documents'], results['metadatas']):
                    memories.append(Memory(
                        id=meta['id'],
                        content=doc,
                        memory_type=meta['memory_type'],
                        importance=meta['importance'],
                        source=meta['source'],
                        created_at=datetime.fromisoformat(meta['created_at']),
                        updated_at=datetime.fromisoformat(meta['updated_at']),
                        metadata=meta.get('metadata', {}),
                    ))
            
            return memories
            
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return []
    
    async def extract_and_store(
        self,
        conversation_text: str,
        llm_provider=None,
    ) -> List[Memory]:
        """
        Extract important information from conversation and store as memories
        
        Args:
            conversation_text: Conversation text to analyze
            llm_provider: LLM provider for extraction (optional)
            
        Returns:
            List of extracted and stored memories
        """
        logger.info("Extracting memories from conversation...")
        
        # If LLM provider available, use intelligent extraction
        if llm_provider:
            from ..llm.prompts import PromptTemplates
            
            prompt = PromptTemplates.get_memory_extraction_prompt(
                conversation_text
            )
            
            try:
                response = await llm_provider.chat([
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Please extract memories."},
                ])
                
                # Parse JSON response
                import json
                extracted = json.loads(response.content)
                memories_data = extracted.get("memories", [])
                
                if memories_data:
                    stored = await self.add_memories_batch(memories_data)
                    logger.info(
                        f"Extracted and stored {len(stored)} memories"
                    )
                    return stored
                    
            except Exception as e:
                logger.warning(f"LLM extraction failed: {e}, using fallback")
        
        # Fallback: store entire conversation as context memory
        memory = await self.add_memory(
            content=conversation_text[:1000],  # Limit length
            memory_type="context",
            importance="low",
            source="conversation_fallback",
        )
        
        return [memory]
    
    @property
    def count(self) -> int:
        """Total number of stored memories"""
        if self._collection:
            return self._collection.count()
        return 0
    
    @property
    def is_initialized(self) -> bool:
        """Check if memory system is initialized"""
        return self._initialized
    
    async def close(self) -> None:
        """Close the database connection"""
        if self._client:
            self._client = None
            self._initialized = False
            logger.debug("Long-term memory closed")
    
    def __repr__(self) -> str:
        return (
            f"LongTermMemory(collection={self.collection_name}, "
            f"count={self.count}, initialized={self._initialized})"
        )
