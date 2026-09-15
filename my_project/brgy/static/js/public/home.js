        // 1. Interactive Mouse-Following Glow in Hero
        const hero = document.querySelector('.landing-hero');
        const glow = document.getElementById('heroGlow');

        if (hero && glow) {
            hero.addEventListener('mousemove', (e) => {
                const rect = hero.getBoundingClientRect();
                glow.style.left = `${e.clientX - rect.left}px`;
                glow.style.top = `${e.clientY - rect.top}px`;
            });
        }

        // 2. Scroll Reveal Animations (Intersection Observer)
        const revealElements = document.querySelectorAll('.reveal, .reveal-left, .reveal-right');
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    // Optional: Stop observing once animated to save resources
                    // observer.unobserve(entry.target); 
                }
            });
        }, {
            threshold: 0.15, // Trigger when 15% of the element is visible
            rootMargin: '0px 0px -50px 0px' // Slight offset from bottom
        });

        revealElements.forEach(el => observer.observe(el));

        // 3. 3D Tilt Effect on Feature Cards
        const tiltCards = document.querySelectorAll('[data-tilt]');
        
        tiltCards.forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                const centerX = rect.width / 2;
                const centerY = rect.height / 2;
                
                // Calculate rotation (max 8 degrees)
                const rotateX = ((y - centerY) / centerY) * -8;
                const rotateY = ((x - centerX) / centerX) * 8;
                
                card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-8px) scale3d(1.02, 1.02, 1.02)`;
            });

            card.addEventListener('mouseleave', () => {
                // Smoothly reset to original state
                card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0px) scale3d(1, 1, 1)';
                card.style.transition = 'transform 0.5s ease';
                setTimeout(() => card.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)', 500);
            });

            card.addEventListener('mouseenter', () => {
                card.style.transition = 'none'; // Remove transition during active tilt for instant response
            });
        });
