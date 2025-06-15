document.addEventListener('DOMContentLoaded', function() {
    const priceElements = document.querySelectorAll('.ad-price');
    
    function formatPrice(price) {
        const num = price.toString().replace(/\D/g, '');
        return num.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    }
    
    priceElements.forEach(el => {
        const originalPrice = el.textContent.trim().replace('₽', '').trim();
        const formattedPrice = formatPrice(originalPrice);
        el.textContent = `${formattedPrice} ₽`;
    });
});