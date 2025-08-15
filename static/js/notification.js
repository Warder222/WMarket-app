// Функция для показа уведомлений
function showNotification(message, type = 'info', duration = 5000) {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, duration);
}

// Стили для уведомлений (добавляем динамически)
const notificationStyles = `
.notification {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    background-color: var(--primary-color);
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    z-index: 1100;
    display: flex;
    align-items: center;
    justify-content: center;
    max-width: 90%;
    text-align: center;
    animation: fadeIn 0.3s ease-out;
}

.notification.error {
    background-color: #F44336;
}

.notification.success {
    background-color: #4CAF50;
}

@keyframes fadeIn {
    from { opacity: 0; top: 0; }
    to { opacity: 1; top: 20px; }
}
`;

// Добавляем стили в head
const styleElement = document.createElement('style');
styleElement.textContent = notificationStyles;
document.head.appendChild(styleElement);