// DOM が読み込まれた後に実行
document.addEventListener('DOMContentLoaded', function() {
    // スムーススクロールの実装
    initSmoothScroll();
    
    // ナビゲーションハイライト
    initNavigationHighlight();
    
    // アニメーション効果
    initScrollAnimations();
    
    // モバイルナビゲーション
    initMobileNavigation();
    
    // コピー機能
    initCopyToClipboard();
    
    // フォームバリデーション（今後追加予定）
    initFormValidation();
    
    // FAQ アコーディオン
    initFAQAccordion();
});

/**
 * スムーススクロールの実装
 */
function initSmoothScroll() {
    // アンカーリンクにスムーススクロールを適用
    const anchorLinks = document.querySelectorAll('a[href^="#"]');
    
    anchorLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);
            
            if (targetElement) {
                const headerHeight = document.querySelector('header').offsetHeight;
                const targetPosition = targetElement.offsetTop - headerHeight - 20;
                
                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });
}

/**
 * ナビゲーションハイライト
 */
function initNavigationHighlight() {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('nav a[href^="#"]');
    
    if (sections.length === 0 || navLinks.length === 0) return;
    
    window.addEventListener('scroll', function() {
        const scrollPosition = window.scrollY + 200;
        
        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.offsetHeight;
            const sectionId = section.getAttribute('id');
            
            if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
                // 現在のセクションに対応するナビリンクをハイライト
                navLinks.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${sectionId}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    });
}

/**
 * スクロールアニメーション
 */
function initScrollAnimations() {
    // Intersection Observer を使用してスクロールアニメーションを実装
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-in');
            }
        });
    }, observerOptions);
    
    // アニメーション対象の要素を監視
    const animateElements = document.querySelectorAll('.feature-card, .command-card, .tech-item, .step');
    animateElements.forEach(element => {
        element.classList.add('animate-ready');
        observer.observe(element);
    });
}

/**
 * モバイルナビゲーション
 */
function initMobileNavigation() {
    const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (mobileMenuToggle && navMenu) {
        mobileMenuToggle.addEventListener('click', function() {
            navMenu.classList.toggle('mobile-open');
            
            // ハンバーガーメニューのアニメーション
            const spans = mobileMenuToggle.querySelectorAll('span');
            spans.forEach(span => {
                span.classList.toggle('active');
            });
        });
        
        // メニュー項目がクリックされた時にメニューを閉じる
        const navLinks = navMenu.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                navMenu.classList.remove('mobile-open');
                const spans = mobileMenuToggle.querySelectorAll('span');
                spans.forEach(span => {
                    span.classList.remove('active');
                });
            });
        });
        
        // 画面サイズが変更された時の処理
        window.addEventListener('resize', function() {
            if (window.innerWidth > 768) {
                navMenu.classList.remove('mobile-open');
                const spans = mobileMenuToggle.querySelectorAll('span');
                spans.forEach(span => {
                    span.classList.remove('active');
                });
            }
        });
    }
}

/**
 * コピー機能
 */
function initCopyToClipboard() {
    // コードブロックにコピーボタンを追加
    const codeBlocks = document.querySelectorAll('pre code');
    
    codeBlocks.forEach(codeBlock => {
        const pre = codeBlock.parentElement;
        const copyButton = document.createElement('button');
        copyButton.textContent = 'コピー';
        copyButton.classList.add('copy-button');
        copyButton.style.cssText = `
            position: absolute;
            top: 10px;
            right: 10px;
            background: #5865F2;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.8rem;
            opacity: 0;
            transition: opacity 0.3s ease;
            box-shadow: 0 2px 4px rgba(88, 101, 242, 0.2);
        `;
        
        pre.style.position = 'relative';
        pre.appendChild(copyButton);
        
        // ホバー時にコピーボタンを表示
        pre.addEventListener('mouseenter', () => {
            copyButton.style.opacity = '1';
        });
        
        pre.addEventListener('mouseleave', () => {
            copyButton.style.opacity = '0';
        });
        
        // コピー機能
        copyButton.addEventListener('click', async function() {
            const text = codeBlock.textContent;
            
            try {
                await navigator.clipboard.writeText(text);
                copyButton.textContent = 'コピー完了!';
                setTimeout(() => {
                    copyButton.textContent = 'コピー';
                }, 2000);
            } catch (err) {
                console.error('コピーに失敗しました:', err);
                copyButton.textContent = 'エラー';
                setTimeout(() => {
                    copyButton.textContent = 'コピー';
                }, 2000);
            }
        });
    });
}

/**
 * FAQ アコーディオン機能
 */
function initFAQAccordion() {
    const faqItems = document.querySelectorAll('.faq-item');
    
    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');
        const answer = item.querySelector('.faq-answer');
        const toggle = item.querySelector('.faq-toggle');
        
        if (question && answer && toggle) {
            question.addEventListener('click', function() {
                const isActive = item.classList.contains('active');
                
                // 他のFAQアイテムを閉じる
                faqItems.forEach(otherItem => {
                    if (otherItem !== item) {
                        otherItem.classList.remove('active');
                    }
                });
                
                // 現在のアイテムをトグル
                if (isActive) {
                    item.classList.remove('active');
                } else {
                    item.classList.add('active');
                }
            });
        }
    });
}

/**
 * フォームバリデーション（今後の拡張用）
 */
function initFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
            }
        });
    });
}

/**
 * フォームバリデーション関数
 */
function validateForm(form) {
    let isValid = true;
    const inputs = form.querySelectorAll('input[required], textarea[required]');
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            showError(input, 'この項目は必須です');
            isValid = false;
        } else {
            clearError(input);
        }
    });
    
    return isValid;
}

/**
 * エラー表示
 */
function showError(input, message) {
    clearError(input);
    
    const errorElement = document.createElement('div');
    errorElement.classList.add('error-message');
    errorElement.textContent = message;
    errorElement.style.cssText = `
        color: #dc3545;
        font-size: 0.875rem;
        margin-top: 0.25rem;
    `;
    
    input.parentNode.appendChild(errorElement);
    input.classList.add('error');
}

/**
 * エラークリア
 */
function clearError(input) {
    const errorElement = input.parentNode.querySelector('.error-message');
    if (errorElement) {
        errorElement.remove();
    }
    input.classList.remove('error');
}

/**
 * ユーティリティ: スクロール位置の取得
 */
function getScrollPosition() {
    return window.pageYOffset || document.documentElement.scrollTop;
}

/**
 * ユーティリティ: 要素が画面内にあるかチェック
 */
function isElementInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
}

/**
 * 動的スタイル追加
 */
function addDynamicStyles() {
    const styles = `
        .animate-ready {
            opacity: 0;
            transform: translateY(20px);
            transition: opacity 0.4s ease, transform 0.4s ease;
        }
        
        .animate-in {
            opacity: 1;
            transform: translateY(0);
        }
        
        .nav-links a.active {
            color: #5865F2;
            background: #f8f9fa;
            border-radius: 4px;
            padding: 0.5rem 1rem;
        }
        
        .mobile-open {
            display: flex !important;
            flex-direction: column;
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            padding: 1rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            border-top: 1px solid #e9ecef;
        }
        
        input.error, textarea.error {
            border-color: #dc3545;
            box-shadow: 0 0 0 0.2rem rgba(220, 53, 69, 0.25);
        }
        
        @media (max-width: 768px) {
            .nav-links {
                display: none;
            }
        }
    `;
    
    const styleSheet = document.createElement('style');
    styleSheet.textContent = styles;
    document.head.appendChild(styleSheet);
}

// 動的スタイルを追加
addDynamicStyles();

/**
 * パフォーマンス最適化: スクロールイベントのスロットリング
 */
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// スクロールイベントをスロットリング
window.addEventListener('scroll', throttle(function() {
    // ここに重い処理がある場合はスロットリングを適用
}, 100));

/**
 * ダークモード対応（今後の拡張用）
 */
function initDarkMode() {
    const darkModeToggle = document.querySelector('.dark-mode-toggle');
    
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', function() {
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
        });
        
        // 保存されたダークモード設定を読み込み
        if (localStorage.getItem('darkMode') === 'true') {
            document.body.classList.add('dark-mode');
        }
    }
}

/**
 * アクセシビリティ機能
 */
function initAccessibility() {
    // キーボードナビゲーション
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Tab') {
            document.body.classList.add('keyboard-navigation');
        }
    });
    
    document.addEventListener('mousedown', function() {
        document.body.classList.remove('keyboard-navigation');
    });
    
    // スキップリンク
    const skipLink = document.createElement('a');
    skipLink.href = '#main';
    skipLink.textContent = 'メインコンテンツにスキップ';
    skipLink.classList.add('skip-link');
    skipLink.style.cssText = `
        position: absolute;
        top: -40px;
        left: 6px;
        background: #5865F2;
        color: white;
        padding: 8px;
        text-decoration: none;
        border-radius: 4px;
        z-index: 1000;
        transition: top 0.3s;
        box-shadow: 0 2px 4px rgba(88, 101, 242, 0.3);
    `;
    
    skipLink.addEventListener('focus', function() {
        this.style.top = '6px';
    });
    
    skipLink.addEventListener('blur', function() {
        this.style.top = '-40px';
    });
    
    document.body.insertBefore(skipLink, document.body.firstChild);
}

// 初期化
initDarkMode();
initAccessibility();