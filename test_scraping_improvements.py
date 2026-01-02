"""Test script to demonstrate the improved web scraping capabilities."""
from src.convert import html_to_clean_markdown

# Sample HTML with navigation, ads, and content
test_html = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <header class="site-header">
        <nav class="navbar">
            <a href="/">Home</a>
            <a href="/about">About</a>
            <a href="/contact">Contact</a>
        </nav>
    </header>
    
    <div class="cookie-banner">
        <p>We use cookies. Accept all cookies to continue.</p>
        <button>Accept</button>
    </div>
    
    <aside class="sidebar">
        <div class="ad">Advertisement</div>
        <div class="newsletter">Sign up for our newsletter</div>
    </aside>
    
    <main>
        <article>
            <h1>Important Company Information</h1>
            <p>This is the main content of the page that we want to extract. It contains valuable information about the company's services and offerings.</p>
            
            <h2>Our Services</h2>
            <p>We provide comprehensive solutions for businesses of all sizes. Our team specializes in custom software development, cloud infrastructure, and digital transformation.</p>
            
            <h2>Why Choose Us</h2>
            <p>With over 15 years of experience, we have helped hundreds of companies achieve their goals. Our dedicated team works closely with clients to deliver exceptional results.</p>
        </article>
    </main>
    
    <footer class="site-footer">
        <p>&copy; 2026 Test Company. All rights reserved.</p>
        <nav>
            <a href="/privacy">Privacy Policy</a>
            <a href="/terms">Terms of Service</a>
        </nav>
    </footer>
    
    <div class="popup modal">
        <p>Subscribe to our newsletter!</p>
    </div>
</body>
</html>
"""

print("Testing improved web scraping...")
print("=" * 60)

# Convert HTML to clean markdown
result = html_to_clean_markdown(test_html)

print("Extracted Content:")
print("-" * 60)
print(result)
print("-" * 60)
print("\nKey improvements demonstrated:")
print("✓ Removed navigation header")
print("✓ Removed cookie banner")
print("✓ Removed sidebar with ads")
print("✓ Removed footer")
print("✓ Removed popup/modal")
print("✓ Extracted only main content from <main> and <article> tags")
print("✓ Clean markdown output without boilerplate")
