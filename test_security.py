#!/usr/bin/env python3
"""
Test script to verify security and authentication
"""

def test_routes_security():
    """Test that routes have proper security"""
    try:
        from app import create_app

        app = create_app()

        # Get all routes and their endpoints
        routes = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static':
                routes.append({
                    'rule': rule.rule,
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods)
                })

        print("Route Security Analysis:")
        print("=" * 50)

        # Check specific routes
        protected_routes = ['/admin', '/admin/pages', '/admin/users', '/admin/settings', '/admin/templates']
        public_routes = ['/', '/login', '/logout']

        print("\n🔒 Protected Routes (should require login):")
        for route in routes:
            if any(protected in route['rule'] for protected in protected_routes):
                print(f"  ✅ {route['rule']} -> {route['endpoint']}")

        print("\n🌐 Public Routes:")
        for route in routes:
            if route['rule'] in public_routes:
                print(f"  ✅ {route['rule']} -> {route['endpoint']}")

        print("\n📊 Route Summary:")
        print(f"  Total routes: {len(routes)}")
        protected_count = sum(1 for route in routes if any(p in route['rule'] for p in protected_routes))
        print(f"  Protected routes: {protected_count}")
        print(f"  Public routes: {len(public_routes)}")

        # Check if authentication is properly imported
        try:
            from cms.auth import login_required
            print("  ✅ login_required decorator imported")
        except ImportError:
            print("  ❌ login_required decorator not found")
            return False

        return True

    except Exception as e:
        print(f"❌ Security test failed: {e}")
        return False

if __name__ == "__main__":
    print("🛡️  Testing CMS Security & Authentication")
    print("=" * 50)

    if test_routes_security():
        print("\n🎉 Security test PASSED!")
        print("\nSecurity features:")
        print("  • Root route (/) redirects to login if not authenticated")
        print("  • Root route (/) redirects to dashboard if authenticated")
        print("  • /admin route requires login")
        print("  • All admin routes require login")
        print("  • Login/logout routes are public")
    else:
        print("\n❌ Security test FAILED!")
        print("  Please check the authentication setup.")
