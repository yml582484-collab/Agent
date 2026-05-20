// b1t-AI 前端应用主逻辑
class B1tAIApp {
    constructor() {
        this.messages = [];
        this.chatHistory = [];
        this.currentChatId = null;
        this.reactMode = false;
        this.isLoading = false;
        this.sidebarCollapsed = false;

        this.initElements();
        this.initEventListeners();
        this.restoreSidebarState();
        this.loadChatHistory();
        this.fetchUsageStats();
    }

    // 初始化 DOM 元素
    initElements() {
        this.sidebar = document.getElementById('sidebar');
        this.menuToggle = document.getElementById('menuToggle');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.chatHistoryEl = document.getElementById('chatHistory');
        this.chatTitle = document.getElementById('chatTitle');
        this.welcomeScreen = document.getElementById('welcomeScreen');
        this.messagesContainer = document.getElementById('messagesContainer');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.reactToggle = document.getElementById('reactToggle');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        
        // 余额显示元素
        this.totalBalance = document.getElementById('totalBalance');
        this.toppedUpBalance = document.getElementById('toppedUpBalance');
        this.grantedBalance = document.getElementById('grantedBalance');
        this.balanceStatus = document.getElementById('balanceStatus');
        
        // 统计元素
        this.usageTokens = document.getElementById('usageTokens');
        this.usageCalls = document.getElementById('usageCalls');
        this.lastUpdated = document.getElementById('lastUpdated');
        this.refreshUsageBtn = document.getElementById('refreshUsageBtn');

        // 侧边栏折叠元素
        this.sidebarTouchZone = document.getElementById('sidebarTouchZone');
        this.expandSidebarBtn = document.getElementById('expandSidebarBtn');
    }

    // 初始化事件监听
    initEventListeners() {
        // 菜单切换
        this.menuToggle.addEventListener('click', () => {
            this.sidebar.classList.toggle('open');
        });

        // 新建对话
        this.newChatBtn.addEventListener('click', () => {
            this.startNewChat();
        });

        // 发送消息
        this.sendBtn.addEventListener('click', () => {
            this.sendMessage();
        });

        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // ReAct 模式切换
        this.reactToggle.addEventListener('click', () => {
            this.reactMode = !this.reactMode;
            this.reactToggle.classList.toggle('active', this.reactMode);
        });

        // 自动调整输入框高度
        this.messageInput.addEventListener('input', () => {
            this.autoResizeInput();
        });

        // 快捷操作点击
        document.querySelectorAll('.quick-action').forEach(action => {
            action.addEventListener('click', () => {
                const prompt = action.dataset.prompt;
                this.messageInput.value = prompt;
                this.autoResizeInput();
                this.messageInput.focus();
            });
        });
        
        // 刷新余额
        this.refreshUsageBtn.addEventListener('click', () => {
            this.fetchUsageStats();
        });

        // 侧边栏折叠/展开（使用透明触摸区域）
        if (this.sidebarTouchZone) {
            this.sidebarTouchZone.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleSidebar();
            });
        }

        if (this.expandSidebarBtn) {
            this.expandSidebarBtn.addEventListener('click', () => {
                this.toggleSidebar(true);
            });
        }

        // 点击外部关闭侧边栏
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 768 && 
                !this.sidebar.contains(e.target) && 
                !this.menuToggle.contains(e.target)) {
                this.sidebar.classList.remove('open');
            }
        });
    }

    // 自动调整输入框高度
    autoResizeInput() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 200) + 'px';
    }

    // 显示加载状态
    showLoading(show = true) {
        this.isLoading = show;
        this.loadingOverlay.style.display = show ? 'flex' : 'none';
        this.sendBtn.disabled = show;
        this.messageInput.disabled = show;

        // 更新loading提示文字
        if (show) {
            const loadingText = this.loadingOverlay.querySelector('.loading-text');
            if (loadingText) {
                loadingText.textContent = 'b1t-AI 正在思考...';

                // 启动动态提示
                this._startLoadingAnimation(loadingText);
            }
        } else {
            if (this._loadingTimer) {
                clearInterval(this._loadingTimer);
                this._loadingTimer = null;
            }
        }
    }

    // Loading动画 - 动态更新提示
    _startLoadingAnimation(element) {
        const messages = [
            'b1t-AI 正在思考...',
            'b1t-AI 正在分析任务...',
            'b1t-AI 正在调用工具...',
            'b1t-AI 正在处理中...',
            '⏳ 复杂任务可能需要较长时间...',
        ];

        let index = 0;
        let dotCount = 0;

        // 主提示循环（每3秒切换）
        this._loadingTimer = setInterval(() => {
            index = (index + 1) % messages.length;
            element.textContent = messages[index];
        }, 3000);

        // 点号动画（每500ms）
        setInterval(() => {
            dotCount = (dotCount + 1) % 4;
            const baseText = messages[index % messages.length];
            element.textContent = baseText + '.'.repeat(dotCount);
        }, 500);
    }

    // 开始新对话
    startNewChat() {
        this.messages = [];
        this.currentChatId = 'chat_' + Date.now();
        this.welcomeScreen.style.display = 'flex';
        this.messagesContainer.classList.remove('active');
        this.messagesContainer.innerHTML = '';
        this.chatTitle.textContent = '新对话';
        this.messageInput.value = '';
        this.autoResizeInput();
        
        // 更新历史记录高亮
        this.updateHistoryHighlight();
        
        // 移动端关闭侧边栏
        if (window.innerWidth <= 768) {
            this.sidebar.classList.remove('open');
        }
    }

    // 加载对话历史
    loadChatHistory() {
        const saved = localStorage.getItem('b1tai_history');
        if (saved) {
            this.chatHistory = JSON.parse(saved);
            this.renderChatHistory();
        }
    }

    // 保存对话历史
    saveChatHistory() {
        if (this.messages.length > 0) {
            const chatItem = {
                id: this.currentChatId,
                title: this.getChatTitle(),
                timestamp: new Date().toISOString(),
                messages: this.messages
            };

            // 查找是否已存在
            const index = this.chatHistory.findIndex(c => c.id === this.currentChatId);
            if (index >= 0) {
                this.chatHistory[index] = chatItem;
            } else {
                this.chatHistory.unshift(chatItem);
                // 只保留最近 50 个对话
                if (this.chatHistory.length > 50) {
                    this.chatHistory = this.chatHistory.slice(0, 50);
                }
            }

            localStorage.setItem('b1tai_history', JSON.stringify(this.chatHistory));
            this.renderChatHistory();
        }
    }

    // 获取对话标题
    getChatTitle() {
        const firstMessage = this.messages.find(m => m.role === 'user');
        if (firstMessage) {
            const title = firstMessage.content.slice(0, 30);
            return title.length < firstMessage.content.length ? title + '...' : title;
        }
        return '新对话';
    }

    // 渲染对话历史
    renderChatHistory() {
        this.chatHistoryEl.innerHTML = '';
        
        this.chatHistory.forEach(chat => {
            const item = document.createElement('div');
            item.className = 'history-item' + (chat.id === this.currentChatId ? ' active' : '');
            item.textContent = chat.title || '新对话';
            item.addEventListener('click', () => {
                this.loadChat(chat.id);
            });
            this.chatHistoryEl.appendChild(item);
        });
    }

    // 更新历史记录高亮
    updateHistoryHighlight() {
        document.querySelectorAll('.history-item').forEach(item => {
            item.classList.remove('active');
        });
    }

    // 加载历史对话
    loadChat(chatId) {
        const chat = this.chatHistory.find(c => c.id === chatId);
        if (chat) {
            this.currentChatId = chatId;
            this.messages = chat.messages;
            this.renderMessages();
            this.chatTitle.textContent = chat.title || '新对话';
            this.welcomeScreen.style.display = 'none';
            this.messagesContainer.classList.add('active');
            
            // 移动端关闭侧边栏
            if (window.innerWidth <= 768) {
                this.sidebar.classList.remove('open');
            }
        }
    }

    // 发送消息
    async sendMessage() {
        const content = this.messageInput.value.trim();
        if (!content || this.isLoading) return;

        // 隐藏欢迎界面
        this.welcomeScreen.style.display = 'none';
        this.messagesContainer.classList.add('active');

        // 添加用户消息
        this.addMessage('user', content);
        this.messageInput.value = '';
        this.autoResizeInput();

        // 发送到后端
        await this.sendToAPI(content);
    }

    // 添加消息到界面
    addMessage(role, content, thinking = null) {
        const message = {
            role,
            content,
            timestamp: new Date().toISOString(),
            thinking
        };
        this.messages.push(message);

        // 如果是新对话，生成 ID
        if (!this.currentChatId) {
            this.currentChatId = 'chat_' + Date.now();
        }

        // 更新标题
        if (role === 'user' && this.messages.filter(m => m.role === 'user').length === 1) {
            this.chatTitle.textContent = this.getChatTitle();
        }

        this.renderMessages();
        this.saveChatHistory();
    }

    // 渲染所有消息
    renderMessages() {
        this.messagesContainer.innerHTML = '';
        
        this.messages.forEach(msg => {
            const el = this.createMessageElement(msg);
            this.messagesContainer.appendChild(el);
        });

        // 滚动到底部
        this.scrollToBottom();
    }

    // 创建消息元素
    createMessageElement(message) {
        const div = document.createElement('div');
        div.className = `message ${message.role}`;
        
        const time = new Date(message.timestamp).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit'
        });

        const avatarSVG = message.role === 'assistant' 
            ? `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                 <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="white"/>
                 <path d="M2 17L12 22L22 17" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                 <path d="M2 12L12 17L22 12" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
               </svg>`
            : `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                 <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                 <circle cx="12" cy="7" r="4" fill="white"/>
               </svg>`;

        div.innerHTML = `
            <div class="message-avatar">${avatarSVG}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-role">${message.role === 'assistant' ? 'b1t-AI' : '你'}</span>
                    <span class="message-time">${time}</span>
                </div>
                <div class="message-body">${this.formatMessage(message.content)}</div>
                ${message.thinking ? this.renderThinking(message.thinking) : ''}
            </div>
        `;

        return div;
    }

    // 格式化消息内容（简单 Markdown）
    formatMessage(content) {
        let formatted = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // 代码块
        formatted = formatted.replace(/```([\s\S]*?)```/g, (match, code) => {
            return `<pre><code>${code.trim()}</code></pre>`;
        });

        // 行内代码
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

        // 换行
        formatted = formatted.replace(/\n/g, '<br>');

        return formatted;
    }

    // 渲染思考过程
    renderThinking(thinking) {
        if (!thinking || thinking.length === 0) return '';
        
        let html = '<div class="thinking-bubble">';
        thinking.forEach((step, index) => {
            html += `
                <div class="thinking-step">
                    <span class="thinking-label">${index + 1}</span>
                    <div class="thinking-content">
                        <div><strong>思考:</strong> ${step.thought || '-'}</div>
                        ${step.action ? `<div><strong>行动:</strong> ${step.action}</div>` : ''}
                        ${step.observation ? `<div><strong>观察:</strong> ${step.observation}</div>` : ''}
                    </div>
                </div>
            `;
        });
        html += '</div>';
        return html;
    }

    // 发送到后端 API
    async sendToAPI(content) {
        this.showLoading(true);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: content,
                    use_react: this.reactMode
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            if (data.success) {
                // 添加助手回复
                this.addMessage('assistant', data.response, data.reasoning_trace || null);
            } else {
                this.addMessage('assistant', '抱歉，出现了一些问题：' + (data.error || '未知错误'));
            }
        } catch (error) {
            console.error('Error:', error);
            this.addMessage('assistant', 
                '抱歉，连接服务器时出现了问题。请检查：\n' +
                '1. 后端服务是否正在运行\n' +
                '2. API Key 是否正确配置\n\n' +
                '错误信息：' + error.message
            );
        } finally {
            this.showLoading(false);
            this.fetchUsageStats(); // 发送完消息后刷新余额
        }
    }
    
    // 获取 API 使用情况和真实余额
    async fetchUsageStats() {
        try {
            const response = await fetch('/api/usage');
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // 更新显示
            this.updateUsageDisplay(data);
            
        } catch (error) {
            console.error('Failed to fetch usage stats:', error);
            this.updateErrorDisplay(error.message);
        }
    }
    
    // 更新使用情况显示（真实余额）
    updateUsageDisplay(data) {
        // 更新余额信息
        const balance = data.balance || {};
        const totalBalance = balance.total_balance || 0;
        const toppedUpBalance = balance.topped_up_balance || 0;
        const grantedBalance = balance.granted_balance || 0;
        
        this.totalBalance.textContent = `¥ ${totalBalance.toFixed(2)}`;
        this.toppedUpBalance.textContent = `¥ ${toppedUpBalance.toFixed(2)}`;
        this.grantedBalance.textContent = `¥ ${grantedBalance.toFixed(2)}`;
        
        // 更新状态指示器
        const isAvailable = data.is_available;
        const statusDot = this.balanceStatus.querySelector('.status-dot');
        const statusText = this.balanceStatus.querySelector('span:last-child');
        
        if (isAvailable) {
            statusDot.className = 'status-dot available';
            statusText.textContent = '可用';
        } else {
            statusDot.className = 'status-dot error';
            statusText.textContent = '不可用';
        }
        
        // 更新本地统计
        const tokenUsage = data.token_usage || {};
        const totalTokens = tokenUsage.total_tokens || 0;
        this.usageTokens.textContent = totalTokens.toLocaleString();
        this.usageCalls.textContent = (data.api_calls || 0).toString();
        
        // 更新最后刷新时间
        if (data.last_updated) {
            const date = new Date(data.last_updated);
            this.lastUpdated.textContent = date.toLocaleTimeString('zh-CN', { 
                hour: '2-digit', 
                minute: '2-digit',
                second: '2-digit'
            });
        }
    }
    
    // 显示错误状态
    updateErrorDisplay(errorMessage) {
        this.totalBalance.textContent = '¥ --';
        this.toppedUpBalance.textContent = '¥ --';
        this.grantedBalance.textContent = '¥ --';
        
        const statusDot = this.balanceStatus.querySelector('.status-dot');
        const statusText = this.balanceStatus.querySelector('span:last-child');
        statusDot.className = 'status-dot error';
        statusText.textContent = '获取失败';
        
        this.lastUpdated.textContent = '--:--';
    }

    // 滚动到底部
    scrollToBottom() {
        setTimeout(() => {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }, 100);
    }

    // 切换侧边栏状态
    toggleSidebar(forceExpand = false) {
        if (forceExpand) {
            this.sidebarCollapsed = false;
        } else {
            this.sidebarCollapsed = !this.sidebarCollapsed;
        }
        
        this.sidebar.classList.toggle('collapsed', this.sidebarCollapsed);
        
        if (this.expandSidebarBtn) {
            this.expandSidebarBtn.style.display = (this.sidebarCollapsed || window.innerWidth <= 768) ? 'flex' : 'none';
        }
        
        localStorage.setItem('b1tai_sidebar_collapsed', JSON.stringify(this.sidebarCollapsed));
    }

    // 恢复侧边栏状态
    restoreSidebarState() {
        const saved = localStorage.getItem('b1tai_sidebar_collapsed');
        if (saved !== null) {
            this.sidebarCollapsed = JSON.parse(saved);
            this.sidebar.classList.toggle('collapsed', this.sidebarCollapsed);
            if (this.expandSidebarBtn) {
                this.expandSidebarBtn.style.display = (this.sidebarCollapsed || window.innerWidth <= 768) ? 'flex' : 'none';
            }
        }

        window.addEventListener('resize', () => {
            if (window.innerWidth <= 768) {
                if (this.expandSidebarBtn) {
                    this.expandSidebarBtn.style.display = 'flex';
                }
            } else {
                if (this.expandSidebarBtn && !this.sidebarCollapsed) {
                    this.expandSidebarBtn.style.display = 'none';
                }
            }
        });
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.b1tAI = new B1tAIApp();
    console.log('🚀 b1t-AI 前端已加载');
});