# Devall CMS

A simple, one-file Flask-based Content Management System with Bootstrap UI and SQLite database.

## Features

- **Admin User Management**: Create, edit, and manage admin users
- **Template System**: Create reusable template blocks (System and Content templates)
- **Page Management**: Build pages using template blocks with drag-and-drop sorting
- **Static Site Generation**: Generate static HTML files for public pages
- **Settings Management**: Configure site-wide settings
- **Bootstrap UI**: Modern, responsive admin interface
- **Preview & Publish**: Preview pages before publishing them

## Installation

1. Ensure you have Python 3.7+ installed
2. Install required dependencies:
   ```bash
   pip install flask
   ```

## Important Note

This CMS is designed as a **single file** application. All templates are embedded directly in the Python code using `render_template_string()` instead of separate HTML files. This eliminates the need for a templates directory and makes the entire application portable in one file.

## Template Override Awareness

The CMS provides **smart template management** with override tracking:

- ✅ **Override Counter**: Templates list shows how many pages are overriding each template
- ✅ **Impact Analysis**: When editing a template, see exactly which pages use custom content
- ✅ **Safe Editing**: Know the impact of template changes before making them
- ✅ **Quick Navigation**: Direct links to edit pages that override templates

### Template Override Features:

1. **Templates List View**:
   - Shows override count with warning badges for templates being customized
   - Helps identify which templates are most frequently customized

2. **Template Edit View**:
   - Displays list of pages overriding the current template
   - Provides direct links to edit those pages
   - Warns about changes not affecting overridden pages

## User Experience Features

- ✅ **Streamlined Interface**: Save and navigation buttons moved to the top for better workflow
- ✅ **Quick Actions**: All page management actions accessible from the top button bar
- ✅ **Improved UX**: No need to scroll to bottom to save changes
- ✅ **Logical Button Order**: Back → Save → Preview → Publish → Delete for optimal workflow
- ✅ **Visual Hierarchy**: Primary actions (Save, Publish) have filled backgrounds, secondary actions are outlined
- ✅ **Modern Styling**: Pill-shaped buttons with consistent spacing and professional appearance
- ✅ **Import/Export**: Full JSON import/export functionality for pages
- ✅ **Selective Export**: Export specific pages using checkbox selection
- ✅ **Data Portability**: Export all pages with templates, content, and settings
- ✅ **Safe Import**: Option to overwrite existing pages or skip duplicates
- ✅ **Bulk Selection**: Select all/none with master checkbox and individual controls
- ✅ **System Block Hiding**: Hide system template blocks by default in page editor
- ✅ **Toggle Controls**: Show/hide system blocks with button click
- ✅ **Configurable Settings**: Admin setting to control default behavior

## Generated Pages Features

When you publish pages, they are generated as **fully styled static HTML files** with:

- ✅ **Bootstrap 5 CSS** for responsive design and modern styling (added only to published pages)
- ✅ **Bootstrap Icons** for enhanced visual elements (added only to published pages)
- ✅ **Bootstrap JavaScript** for interactive components (dropdowns, navigation, etc.)
- ✅ **Custom styling** optimized for generated pages
- ✅ **Responsive layout** that works on all devices
- ✅ **Professional appearance** ready for production use

The generated pages include all necessary CSS and JavaScript from CDNs, so they work offline and load quickly. The admin interface uses its own Bootstrap CSS and is kept separate from the published pages.

## Import/Export Features

The CMS provides comprehensive **JSON-based import/export** functionality:

### Export Pages
- **Full Data Export**: Exports all pages with their complete template configurations
- **Selective Export**: Export only selected pages using checkboxes
- **Template Relationships**: Includes all page-template relationships and custom content
- **Metadata Preservation**: Maintains creation dates, publish status, and all settings
- **JSON Format**: Clean, readable JSON structure for easy processing
- **One-Click Download**: Automatic file download with proper naming
- **Smart Selection**: Select all/none with master checkbox and individual selection

### Import Pages
- **Smart Conflict Resolution**: Option to overwrite existing pages or skip duplicates
- **Template Mapping**: Automatically handles template relationships during import
- **Data Validation**: Validates JSON structure and handles import errors gracefully
- **Template Validation**: Checks if referenced templates exist before importing
- **Database Commit**: Properly commits all changes to ensure data persistence
- **Bulk Operations**: Import multiple pages at once
- **Progress Feedback**: Clear success/error messages during import

### Selective Export with Checkboxes
1. **Select Pages**: Check individual pages or use the master checkbox to select all
2. **Export Button Appears**: "Export Selected (X)" button appears when pages are selected
3. **Download**: Click to download JSON file with only selected pages
4. **Clear Selection**: Uncheck all to hide the export button

### System Block Management
The CMS provides smart management of system template blocks:

#### Default Hiding
- **System Blocks Hidden**: System template blocks (HTML head, meta tags, etc.) are hidden by default
- **Content Focus**: Focus on content blocks during page editing
- **Clean Interface**: Less cluttered editing experience

#### Toggle Controls
- **Show/Hide Button**: Toggle button in page editor header
- **Dynamic Display**: System blocks can be shown/hidden instantly
- **Visual Feedback**: Button changes icon and color based on state

#### Admin Settings
- **Global Setting**: Configure default behavior in Settings page
- **Per-User Control**: Each admin can set their preferred default
- **Persistent Setting**: Setting is saved and applied across sessions

### JSON Structure
```json
[
  {
    "id": 1,
    "title": "Home Page",
    "slug": "home",
    "published": 1,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
    "templates": [
      {
        "id": 1,
        "template_id": 1,
        "template_title": "Hero Section",
        "template_slug": "hero",
        "custom_content": "<h1>Welcome!</h1>",
        "use_default": 0,
        "sort_order": 0
      }
    ]
  }
]
```

## Running the CMS

1. Run the application:
   ```bash
   python cms.py
   ```

2. Open your browser and navigate to: `http://localhost:5000`

3. Login with default credentials:
   - Username: `admin`
   - Password: `admin123`

## Usage

### First Time Setup

1. **Login**: Use the default admin credentials
2. **Settings**: Update site name, description, and other settings
3. **Templates**: Review and customize the default template blocks
4. **Users**: Create additional admin users if needed

### Creating Pages

1. Go to the **Pages** section
2. Click **"Add Page"**
3. Enter page title and slug (URL-friendly identifier)
4. The page will be created with default template blocks

### Editing Pages

1. From the Pages section, click **"Edit"** on any page
2. **Template Blocks**: Each page consists of template blocks that can be:
   - **Sorted**: Use up/down arrows to reorder blocks
   - **Overridden**: Uncheck "Use default template content" to customize
   - **Saved**: Save changes to preserve custom content

### Publishing Pages

1. **Preview**: Click "Preview" to see how the page will look
2. **Publish**: Click "Publish" to generate static HTML in the `pub/` directory
3. **Access**: Published pages are available as static HTML files

### Template Management

1. Go to **Templates** section
2. **Default Templates** include:
   - Base Header (HTML structure)
   - Meta Tags (SEO and meta information)
   - Header Close (closing head tag)
   - Hero Section (main banner)
   - Navigation Menu
   - Content Section
   - Paragraph
   - Footer

3. **Categories**:
   - **System Templates**: Structural elements (HTML, head, meta, footer)
   - **Content Templates**: Content elements (hero, sections, paragraphs)

## File Structure

```
cms.py          # Main CMS application
cms.db          # SQLite database (created automatically)
pub/            # Generated static HTML files
README.md       # This documentation
```

## Default Templates

The CMS comes with pre-configured template blocks:

1. **Base Header** - HTML document structure
2. **Meta Tags** - SEO and meta information
3. **Header Close** - Closes head tag, opens body
4. **Hero Section** - Main page banner
5. **Navigation Menu** - Site navigation
6. **Content Section** - Main content area
7. **Paragraph** - Text content block
8. **Footer** - Site footer

## Template Variables

The following variables are automatically replaced in templates:

- `{{ page_title }}` - Current page title
- `{{ site_name }}` - Site name from settings
- `{{ site_description }}` - Site description from settings
- `{{ hero_title }}` - Hero section title
- `{{ hero_subtitle }}` - Hero section subtitle
- `{{ section_title }}` - Content section title
- `{{ section_content }}` - Section content
- `{{ paragraph_content }}` - Paragraph text
- `{{ menu_content }}` - Navigation menu content

## Security Notes

- Change the default admin password after first login
- The application runs in debug mode by default
- For production use, set `debug=False` and use a proper WSGI server

## Database Schema

The SQLite database includes these tables:

- `users` - Admin users
- `settings` - CMS configuration
- `templates` - Template blocks
- `pages` - Page definitions
- `page_templates` - Many-to-many relationship between pages and templates

## Customization

### Adding New Templates

1. Go to Templates → Add Template
2. Choose category (System or Content)
3. Set sort order for default inclusion
4. Add HTML content with template variables

### Modifying UI

The admin interface uses Bootstrap 5 and custom CSS. Template strings are embedded in the Python file for easy modification.

## Troubleshooting

- **Database Issues**: Delete `cms.db` and restart to recreate with defaults
- **Port Conflicts**: Change the port in `app.run(port=5000)`
- **Template Errors**: Check template syntax and variable names

## License

This is a basic CMS implementation. Use and modify as needed for your projects.
