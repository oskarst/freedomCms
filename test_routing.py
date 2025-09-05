#!/usr/bin/env python3
"""
Test script to verify routing is working correctly
"""

def test_routing():
    """Test that blueprint routes are correctly registered"""
    try:
        from app import create_app

        app = create_app()

        # Get all routes
        routes = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static':
                routes.append(f"{rule.rule} -> {rule.endpoint}")

        print("Registered routes:")
        for route in sorted(routes):
            print(f"  {route}")

        # Check for expected routes
        expected_routes = [
            '/admin/pages',
            '/admin/users',
            '/admin/settings',
            '/admin/templates',
            '/admin',
            '/',
            '/login',
            '/logout'
        ]

        missing_routes = []
        for expected in expected_routes:
            if not any(expected in route for route in routes):
                missing_routes.append(expected)

        if missing_routes:
            print(f"\n❌ Missing routes: {missing_routes}")
            return False
        else:
            print("\n✅ All expected routes are present")
            return True

    except Exception as e:
        print(f"❌ Routing test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Blueprint Routing")
    print("=" * 40)

    if test_routing():
        print("\n🎉 Routing test PASSED!")
        print("The blueprint routes should now work correctly.")
    else:
        print("\n❌ Routing test FAILED!")
