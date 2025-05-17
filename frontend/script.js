document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const chatOutput = document.getElementById('chat-output');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const themeIcon = document.getElementById('theme-icon');
    const chatContainer = document.querySelector('.chat-container');
    
    // State variables
    let isTyping = false;
    let darkMode = localStorage.getItem('darkMode') === 'true';
    let isMobile = window.innerWidth <= 768;
    
    // Initialize theme
    if (darkMode) {
        document.body.setAttribute('data-theme', 'dark');
        themeIcon.classList.replace('fa-moon', 'fa-sun');
    }
    
    // Theme toggle functionality
    themeIcon.addEventListener('click', () => {
        darkMode = !darkMode;
        localStorage.setItem('darkMode', darkMode);
        
        if (darkMode) {
            document.body.setAttribute('data-theme', 'dark');
            themeIcon.classList.replace('fa-moon', 'fa-sun');
        } else {
            document.body.removeAttribute('data-theme');
            themeIcon.classList.replace('fa-sun', 'fa-moon');
        }
    });
    
    // Auto-resize textarea
    function resizeTextarea() {
        userInput.style.height = 'auto';
        const newHeight = Math.min(userInput.scrollHeight, 120); // Limit max height
        userInput.style.height = newHeight + 'px';
        
    }
    
    userInput.addEventListener('input', resizeTextarea);
    
    // Format current time
    function getCurrentTime() {
        const now = new Date();
        let hours = now.getHours();
        const minutes = now.getMinutes().toString().padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        
        hours = hours % 12;
        hours = hours ? hours : 12; // Convert 0 to 12
        
        return `${hours}:${minutes} ${ampm}`;
    }
    
    // Get current date for timestamp
    function getCurrentDate() {
        const now = new Date();
        const options = { weekday: 'long', month: 'long', day: 'numeric' };
        return now.toLocaleDateString('en-US', options);
    }
    
    // Create typing indicator
    function createTypingIndicator() {
        const typingElement = document.createElement('div');
        typingElement.classList.add('typing-indicator');
        typingElement.innerHTML = `
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        `;
        return typingElement;
    }
    
    // Append a new message to the chat
    function appendMessage(message, sender) {
        // Create message container
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', sender === 'user' ? 'user-message' : 'agent-message');
        
        // Create avatar
        const avatarElement = document.createElement('div');
        avatarElement.classList.add('message-avatar');
        avatarElement.innerHTML = sender === 'user' 
            ? '<i class="fa-solid fa-user"></i>' 
            : '<i class="fa-solid fa-robot"></i>';
        
        // Create message content container
        const contentElement = document.createElement('div');
        contentElement.classList.add('message-content');
        
        // Create message text
        const textElement = document.createElement('div');
        textElement.classList.add('message-text');
        textElement.textContent = message;
        
        // Create message time
        const timeElement = document.createElement('div');
        timeElement.classList.add('message-time');
        timeElement.textContent = getCurrentTime();
        
        // Assemble message
        contentElement.appendChild(textElement);
        contentElement.appendChild(timeElement);
        messageElement.appendChild(avatarElement);
        messageElement.appendChild(contentElement);
        
        // Add timestamp if it's the first message or a new day
        const lastTimestamp = chatOutput.querySelector('.message-timestamp:last-of-type');
        const currentDate = getCurrentDate();
        
        if (!lastTimestamp || lastTimestamp.textContent !== currentDate) {
            const timestampElement = document.createElement('div');
            timestampElement.classList.add('message-timestamp');
            timestampElement.textContent = currentDate;
            chatOutput.appendChild(timestampElement);
        }
        
        // Add message to chat
        chatOutput.appendChild(messageElement);
        
        // Scroll to bottom
        scrollToBottom();
    }
    
    // Smooth scroll to bottom of chat
    function scrollToBottom() {
    // Smoothly scroll to the bottom of the chat container
    chatContainer.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: 'smooth'
    });
    }
    
    // Handle window resize
    function handleResize() {
    // Update CSS variable for input container height (used to pad chat messages)
    const inputContainerHeight = document.querySelector('.input-container').offsetHeight;
    document.documentElement.style.setProperty('--input-container-height', `${inputContainerHeight}px`);

    // Ensure we're scrolled to the bottom after resize
    setTimeout(scrollToBottom, 100);
    }
    
    window.addEventListener('resize', handleResize);
    handleResize(); // Initial call
    
    // Fix for mobile virtual keyboard issues
    window.addEventListener('focusin', (e) => {
        if (e.target === userInput) {
            // On mobile, when keyboard appears, scroll to bottom after a short delay
            if (isMobile) {
                setTimeout(() => {
                    scrollToBottom();
                    document.body.scrollTop = 0;
                    document.documentElement.scrollTop = 0;
                }, 300);
            }
        }
    });
    
    // Handle orientation change specifically
    window.addEventListener('orientationchange', () => {
        // Wait for the orientation change to complete
        setTimeout(() => {
            handleResize();
            scrollToBottom();
        }, 300);
    });
    
    // Send message to backend and handle response
    async function sendMessage() {
        const messageText = userInput.value.trim();
        if (messageText === '') {
            return;
        }
        
        // Reset textarea height
        userInput.value = '';
        userInput.style.height = 'auto';
        
        // Add user message to chat
        appendMessage(messageText, 'user');
        
        // Show typing indicator
        if (!isTyping) {
            isTyping = true;
            const typingIndicator = createTypingIndicator();
            chatOutput.appendChild(typingIndicator);
            scrollToBottom();
            
            try {
                // Simulate network delay (remove in production)
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                // Make API call to backend
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: messageText }),
                });
                
                // Remove typing indicator
                chatOutput.removeChild(typingIndicator);
                isTyping = false;
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                if (data.reply) {
                    appendMessage(data.reply, 'agent');
                } else if (data.error) {
                    appendMessage(`Agent Error: ${data.error}`, 'agent');
                }
            } catch (error) {
                console.error('Error sending message:', error);
                
                // Remove typing indicator if it exists
                if (isTyping) {
                    chatOutput.removeChild(typingIndicator);
                    isTyping = false;
                }
                
                appendMessage(`Sorry, I encountered an error: ${error.message}. Please try again later.`, 'agent');
            }
        }
    }
    
    // Event listeners for sending messages
    sendButton.addEventListener('click', sendMessage);
    
    userInput.addEventListener('keydown', (event) => {
        // Send on Enter, but allow Shift+Enter for new line
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });
    
    // Focus input on page load (with delay for mobile)
    setTimeout(() => {
        userInput.focus();
    }, 300);
    
    // Prevent body scrolling on mobile
    document.body.addEventListener('touchmove', (e) => {
        if (e.target !== chatOutput && !chatOutput.contains(e.target)) {
            e.preventDefault();
        }
    }, { passive: false });
});
