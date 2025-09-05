#!/usr/bin/env python3
"""
Test script for the refactored Devall CMS
"""

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")

    try:
        # Test cms package imports
        from cms.db import get_db, init_db, APP_SECRET, DB_PATH, PUB_DIR
        from cms.utils import slugify, now_iso, fetch_settings
        from cms.auth import bp as auth_bp, login_required, admin_required
        from cms.services.publisher import generate_page_html
        from cms.views.pages import bp as pages_bp
        from cms.views.users import bp as users_bp
        from cms.views.settings import bp as settings_bp
        from cms.views.templates_ import bp as templates_bp

        print("✅ All CMS modules imported successfully")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_app_creation():
    """Test that the Flask app can be created"""
    print("\nTesting app creation...")

    try:
        from app import create_app
        app = create_app()
        print("✅ Flask app created successfully")
        print(f"   - Secret key: {app.config['SECRET_KEY'][:10]}...")
        print(f"   - Template folder: {app.template_folder}")
        return True

    except Exception as e:
        print(f"❌ App creation error: {e}")
        return False

def test_blueprints():
    """Test that blueprints are properly registered"""
    print("\nTesting blueprint registration...")

    try:
        from app import create_app
        app = create_app()

        # Check registered blueprints
        blueprints = list(app.blueprints.keys())
        print(f"✅ Registered blueprints: {blueprints}")

        # Check that expected blueprints are registered
        expected = ['auth', 'pages', 'templates_', 'users', 'settings']
        for bp_name in expected:
            if bp_name not in blueprints:
                print(f"❌ Missing blueprint: {bp_name}")
                return False

        print("✅ All expected blueprints registered")
        return True

    except Exception as e:
        print(f"❌ Blueprint test error: {e}")
        return False

def test_routes():
    """Test that routes are properly registered"""
    print("\nTesting route registration...")

    try:
        from app import create_app
        app = create_app()

        # Get all routes
        routes = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static':
                routes.append(f"{rule.rule} -> {rule.endpoint}")

        print("✅ Routes registered:")
        for route in sorted(routes)[:10]:  # Show first 10
            print(f"   {route}")

        if len(routes) > 10:
            print(f"   ... and {len(routes) - 10} more routes")

        return True

    except Exception as e:
        print(f"❌ Route test error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Refactored Devall CMS")
    print("=" * 50)

    tests = [
        test_imports,
        test_app_creation,
        test_blueprints,
        test_routes
    ]

    results = []
    for test in tests:
        results.append(test())

    print("\n" + "=" * 50)
    if all(results):
        print("🎉 All tests PASSED! Refactoring successful!")
        print("\nTo run the refactored CMS:")
        print("1. python app.py")
        print("2. Open http://localhost:4400")
        print("3. Login with admin/admin123")
    else:
        print("❌ Some tests FAILED!")
        print(f"Results: {sum(results)}/{len(results)} passed")
