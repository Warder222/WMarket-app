// Функция для показа уведомлений
function showNotification(message, type = 'info', duration = 5000) {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // Позиционируем уведомление по центру экрана
    notification.style.top = '50%';
    notification.style.left = '50%';
    notification.style.transform = 'translate(-50%, -150%)';
    notification.style.opacity = '0';
    
    // Запускаем анимацию появления
    requestAnimationFrame(() => {
        notification.style.transform = 'translate(-50%, -50%)';
        notification.style.opacity = '1';
    });
    
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, duration);
}

// Стили для уведомлений (добавляем динамически)
const notificationStyles = `
.notification {
    position: fixed;
    top: 50%;
    left: 50%;
    background-color: var(--primary-color);
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    z-index: 1100;
    display: flex;
    align-items: center;
    justify-content: center;
    max-width: 80%;
    text-align: center;
    transition: transform 0.4s cubic-bezier(0.18, 0.89, 0.32, 1.28), opacity 0.3s ease-out;
    will-change: transform, opacity;
}

.notification.error {
    background-color: #F44336;
}

.notification.success {
    background-color: #4CAF50;
}
`;

// Добавляем стили в head
const styleElement = document.createElement('style');
styleElement.textContent = notificationStyles;
document.head.appendChild(styleElement);