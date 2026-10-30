#!/usr/bin/env python3
"""
C/C++ Code Review Report - Markdown to HTML Converter
Converts the copilot-cpp-review-report.md to a professional styled HTML file.

Usage:
    python generate_report_html.py [input_md] [output_html]
    
    Default input: copilot-cpp-review-report.md
    Default output: copilot-cpp-review-report.html

Author: Zhao Jianbo
Supported by: UX SW AI Community
Version: 1.1.0
"""

__version__ = "1.1.0"

import re
import sys
from pathlib import Path
from datetime import datetime


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        :root {{
            --primary-color: #2c3e50;
            --secondary-color: #3498db;
            --success-color: #27ae60;
            --warning-color: #f39c12;
            --danger-color: #e74c3c;
            --critical-color: #c0392b;
            --medium-color: #e67e22;
            --low-color: #95a5a6;
            --bg-color: #ecf0f1;
            --card-bg: #ffffff;
            --text-color: #2c3e50;
            --border-color: #bdc3c7;
            --code-bg: #f8f9fa;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background: var(--bg-color);
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: var(--card-bg);
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: visible;
        }}

        header {{
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            color: white;
            padding: 40px;
            text-align: center;
            border-radius: 8px 8px 0 0;
        }}

        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        header .subtitle {{
            font-size: 1.2em;
            opacity: 0.9;
        }}

        .nav-bar {{
            background: var(--primary-color);
            padding: 15px 40px;
            position: sticky;
            top: 0;
            z-index: 1000;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}

        .nav-bar ul {{
            list-style: none;
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
        }}

        .nav-bar a {{
            color: white;
            text-decoration: none;
            padding: 5px 10px;
            border-radius: 4px;
            transition: background 0.3s;
        }}

        .nav-bar a:hover {{
            background: var(--secondary-color);
        }}

        .content {{
            padding: 40px;
        }}

        section {{
            margin-bottom: 50px;
        }}

        h2 {{
            color: var(--primary-color);
            font-size: 2em;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid var(--secondary-color);
        }}

        h3 {{
            color: var(--secondary-color);
            font-size: 1.5em;
            margin: 30px 0 15px 0;
        }}

        h4 {{
            color: var(--primary-color);
            font-size: 1.2em;
            margin: 20px 0 10px 0;
        }}

        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .info-card {{
            background: var(--bg-color);
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid var(--secondary-color);
        }}

        .info-card strong {{
            display: block;
            color: var(--primary-color);
            margin-bottom: 5px;
        }}

        .stats-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}

        .stat-card {{
            background: linear-gradient(135deg, var(--secondary-color), var(--primary-color));
            color: white;
            padding: 25px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}

        .stat-card .number {{
            font-size: 3em;
            font-weight: bold;
            display: block;
        }}

        .stat-card .label {{
            font-size: 1.1em;
            opacity: 0.9;
        }}

        .severity-critical {{ background: linear-gradient(135deg, var(--critical-color), #e74c3c); }}
        .severity-high {{ background: linear-gradient(135deg, var(--danger-color), #e67e22); }}
        .severity-medium {{ background: linear-gradient(135deg, var(--medium-color), #f39c12); }}
        .severity-low {{ background: linear-gradient(135deg, var(--low-color), #7f8c8d); }}

        .table-wrapper {{
            width: 100%;
            overflow-x: auto;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-radius: 4px;
        }}

        table {{
            width: 100%;
            min-width: 900px;
            border-collapse: collapse;
            margin: 0;
            background: white;
        }}

        th {{
            background: var(--primary-color);
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }}

        td {{
            padding: 12px 15px;
            border-bottom: 1px solid var(--border-color);
            word-break: break-word;
            overflow-wrap: break-word;
            max-width: 350px;
            white-space: pre-wrap;
        }}

        td code {{
            white-space: pre-wrap;
            word-break: break-all;
        }}

        td pre {{
            margin: 0;
            padding: 8px;
            font-size: 0.85em;
            max-height: 300px;
            overflow-y: auto;
            background: var(--code-bg);
            border-left: 3px solid var(--secondary-color);
            border-radius: 3px;
            white-space: pre-wrap;
            word-break: break-all;
        }}

        tr:hover {{
            background: var(--bg-color);
        }}

        .severity-badge {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
            color: white;
        }}

        .badge-critical {{ background: var(--critical-color); }}
        .badge-high {{ background: var(--danger-color); }}
        .badge-medium {{ background: var(--medium-color); }}
        .badge-low {{ background: var(--low-color); }}

        code {{
            background: var(--code-bg);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.9em;
            color: #c7254e;
        }}

        pre {{
            background: var(--code-bg);
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            border-left: 4px solid var(--secondary-color);
            margin: 15px 0;
        }}

        pre code {{
            background: none;
            padding: 0;
            color: var(--text-color);
        }}

        .recommendation-list {{
            background: #e8f5e9;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid var(--success-color);
            margin: 20px 0;
        }}

        .recommendation-list ul {{
            margin-left: 20px;
        }}

        .recommendation-list li {{
            margin: 10px 0;
        }}

        .positive-finding {{
            background: #e8f5e9;
            border-left: 4px solid var(--success-color);
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
        }}

        .positive-finding::before {{
            content: "✓ ";
            color: var(--success-color);
            font-weight: bold;
            font-size: 1.2em;
        }}

        .warning-box {{
            background: #fff3cd;
            border-left: 4px solid var(--warning-color);
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
        }}

        .warning-box::before {{
            content: "⚠️ ";
            font-weight: bold;
        }}

        .action-table th {{
            background: var(--danger-color);
        }}

        .priority-p0 {{ color: var(--critical-color); font-weight: bold; }}
        .priority-p1 {{ color: var(--danger-color); font-weight: bold; }}
        .priority-p2 {{ color: var(--medium-color); font-weight: bold; }}
        .priority-p3 {{ color: var(--low-color); }}
        .priority-p4 {{ color: var(--low-color); }}

        footer {{
            background: var(--primary-color);
            color: white;
            padding: 30px;
            text-align: center;
            margin-top: 40px;
            border-radius: 0 0 8px 8px;
        }}

        .file-link {{
            color: var(--secondary-color);
            text-decoration: none;
            font-weight: 500;
        }}

        .file-link:hover {{
            text-decoration: underline;
        }}

        ol, ul {{
            margin-left: 30px;
        }}

        li {{
            margin: 10px 0;
        }}

        p {{
            margin: 10px 0;
        }}

        blockquote {{
            border-left: 4px solid var(--secondary-color);
            padding-left: 20px;
            margin: 20px 0;
            color: #555;
            font-style: italic;
        }}

        @media print {{
            body {{
                background: white;
            }}
            .nav-bar {{
                display: none;
            }}
            .container {{
                box-shadow: none;
            }}
            section {{
                page-break-inside: avoid;
            }}
        }}

        @media (max-width: 768px) {{
            .content {{
                padding: 20px;
            }}
            header {{
                padding: 20px;
            }}
            header h1 {{
                font-size: 1.8em;
            }}
            .stats-container {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 C/C++ Code Review Report</h1>
            <p class="subtitle">{subtitle}</p>
            <p style="margin-top: 10px; opacity: 0.8;">Generated: {timestamp} | Standard: MISRA C:2023</p>
        </header>

        <nav class="nav-bar">
            <ul>
                <li><a href="#header">📊 Header</a></li>
                <li><a href="#overview">📋 Overview</a></li>
                <li><a href="#issues">🐛 Issues</a></li>
                <li><a href="#themes">🎯 Analysis</a></li>
                <li><a href="#testing">🧪 Testing</a></li>
                <li><a href="#deviations">📝 Deviations</a></li>
                <li><a href="#appendix">📚 Appendix</a></li>
            </ul>
        </nav>

        <div class="content">
{content}
        </div>

        <footer>
            <h3>Report Generation</h3>
            {footer}
        </footer>
    </div>

    <script>
        // Smooth scrolling for navigation links
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
            anchor.addEventListener('click', function (e) {{
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {{
                    target.scrollIntoView({{
                        behavior: 'smooth',
                        block: 'start'
                    }});
                }}
            }});
        }});

        // Add print button functionality
        const printBtn = document.createElement('button');
        printBtn.textContent = '🖨️ Print Report';
        printBtn.style.cssText = 'position: fixed; bottom: 30px; right: 30px; padding: 15px 25px; background: var(--secondary-color); color: white; border: none; border-radius: 30px; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.2); font-size: 16px; z-index: 1000;';
        printBtn.onclick = () => window.print();
        document.body.appendChild(printBtn);

        // Highlight current section in navigation
        window.addEventListener('scroll', () => {{
            const sections = document.querySelectorAll('section');
            const navLinks = document.querySelectorAll('.nav-bar a');
            
            let current = '';
            sections.forEach(section => {{
                const sectionTop = section.offsetTop;
                if (pageYOffset >= sectionTop - 100) {{
                    current = section.getAttribute('id');
                }}
            }});

            navLinks.forEach(link => {{
                link.style.background = '';
                if (link.getAttribute('href') === `#${{current}}`) {{
                    link.style.background = 'var(--secondary-color)';
                }}
            }});
        }});
    </script>
</body>
</html>
"""


class MarkdownToHTMLConverter:
    """Converts structured markdown report to styled HTML."""
    
    def __init__(self):
        self.in_table = False
        self.in_code_block = False
        self.in_list = False
        self.section_counter = 0
        self.current_section_id = ""
        
    def convert_inline_markdown(self, text):
        """Convert inline markdown syntax to HTML."""
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Inline code
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        # Links - markdown style [text](url)
        text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" class="file-link">\1</a>', text)
        return text
    
    def detect_severity_badge(self, text):
        """Detect and convert severity indicators to badges."""
        for severity in ['Critical', 'High', 'Medium', 'Low']:
            if severity in text:
                badge_class = f'badge-{severity.lower()}'
                text = text.replace(severity, f'<span class="severity-badge {badge_class}">{severity}</span>')
        return text
    
    def parse_header_info(self, lines):
        """Parse the header section for metadata."""
        info = {
            'project_path': '',
            'generation_time': '',
            'files_reviewed': '',
            'severity_stats': {'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0},
            'misra_stats': {}
        }
        
        for line in lines:
            if 'Project Path' in line:
                info['project_path'] = line.split(':', 1)[1].strip().strip('`')
            elif 'Generation Time' in line:
                info['generation_time'] = line.split(':', 1)[1].strip()
            elif 'Critical:' in line:
                # Parse: Critical: 0 | High: 0 | Medium: 3 | Low: 3
                matches = re.findall(r'(\w+):\s*(\d+)', line)
                for severity, count in matches:
                    info['severity_stats'][severity] = int(count)
        
        return info
    
    def create_section_header(self, title, section_num):
        """Create a section header with ID for navigation."""
        section_ids = {
            '1': 'header',
            '2': 'overview',
            '3': 'issues',
            '4': 'themes',
            '5': 'testing',
            '6': 'deviations',
            '7': 'appendix'
        }
        section_id = section_ids.get(str(section_num), f'section-{section_num}')
        return f'            <section id="{section_id}">\n                <h2>{title}</h2>\n'
    
    def parse_table(self, lines, start_idx):
        """Parse markdown table to HTML."""
        html = '                <div class="table-wrapper">\n                <table>\n'
        
        # Find table boundaries
        end_idx = start_idx
        while end_idx < len(lines) and lines[end_idx].strip().startswith('|'):
            end_idx += 1
        
        table_lines = lines[start_idx:end_idx]
        if len(table_lines) < 2:
            return html + '                </table>\n', end_idx
        
        # Parse header
        headers = [h.strip() for h in table_lines[0].split('|')[1:-1]]
        html += '                    <thead>\n                        <tr>\n'
        for header in headers:
            html += f'                            <th>{self.convert_inline_markdown(header)}</th>\n'
        html += '                        </tr>\n                    </thead>\n'
        
        # Parse body (skip separator line at index 1)
        html += '                    <tbody>\n'
        for line in table_lines[2:]:
            cells = [c.strip() for c in line.split('|')[1:-1]]
            html += '                        <tr>\n'
            for cell in cells:
                cell_html = self.convert_inline_markdown(cell)
                cell_html = self.detect_severity_badge(cell_html)
                # Add priority classes
                if cell.startswith('P0') or cell.startswith('**P0'):
                    html += f'                            <td class="priority-p0">{cell_html}</td>\n'
                elif cell.startswith('P1'):
                    html += f'                            <td class="priority-p1">{cell_html}</td>\n'
                elif cell.startswith('P2'):
                    html += f'                            <td class="priority-p2">{cell_html}</td>\n'
                elif cell.startswith('P3'):
                    html += f'                            <td class="priority-p3">{cell_html}</td>\n'
                elif cell.startswith('P4'):
                    html += f'                            <td class="priority-p4">{cell_html}</td>\n'
                else:
                    html += f'                            <td>{cell_html}</td>\n'
            html += '                        </tr>\n'
        html += '                    </tbody>\n'
        
        html += '                </table>\n                </div>\n'
        return html, end_idx
    
    def convert_to_html(self, markdown_text):
        """Convert markdown text to HTML."""
        lines = markdown_text.split('\n')
        html_content = []
        
        i = 0
        current_section = None
        header_info = None
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Section headers (## heading)
            if line.startswith('## '):
                if current_section:
                    html_content.append('            </section>\n')
                
                title = line[3:].strip()
                section_match = re.match(r'(\d+)\.\s*(.+)', title)
                if section_match:
                    section_num = section_match.group(1)
                    section_title = section_match.group(2)
                    current_section = self.create_section_header(f'{section_num}. {section_title}', section_num)
                else:
                    current_section = f'            <section>\n                <h2>{title}</h2>\n'
                
                html_content.append(current_section)
                i += 1
                continue
            
            # Subsection headers (### or ####)
            if line.startswith('### '):
                title = self.convert_inline_markdown(line[4:].strip())
                html_content.append(f'                <h3>{title}</h3>\n')
                i += 1
                continue
            
            if line.startswith('#### '):
                title = self.convert_inline_markdown(line[5:].strip())
                html_content.append(f'                <h4>{title}</h4>\n')
                i += 1
                continue
            
            # Code blocks
            if line.startswith('```'):
                html_content.append('                <pre><code>')
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    # Escape HTML in code
                    code_line = lines[i].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    html_content.append(code_line + '\n')
                    i += 1
                html_content.append('</code></pre>\n')
                i += 1
                continue
            
            # Tables
            if line.startswith('|'):
                table_html, new_idx = self.parse_table(lines, i)
                html_content.append(table_html)
                i = new_idx
                continue
            
            # Lists
            if line.startswith('- ') or re.match(r'^\d+\.\s', line):
                list_type = 'ul' if line.startswith('- ') else 'ol'
                html_content.append(f'                <{list_type}>\n')
                
                while i < len(lines) and (lines[i].strip().startswith('- ') or re.match(r'^\d+\.\s', lines[i].strip())):
                    item = re.sub(r'^-\s+|\d+\.\s+', '', lines[i].strip())
                    item_html = self.convert_inline_markdown(item)
                    html_content.append(f'                    <li>{item_html}</li>\n')
                    i += 1
                
                html_content.append(f'                </{list_type}>\n')
                continue
            
            # Blockquotes
            if line.startswith('>'):
                html_content.append('                <blockquote>\n')
                while i < len(lines) and lines[i].strip().startswith('>'):
                    quote_text = self.convert_inline_markdown(lines[i].strip()[1:].strip())
                    html_content.append(f'                    <p>{quote_text}</p>\n')
                    i += 1
                html_content.append('                </blockquote>\n')
                continue
            
            # Special boxes
            if '✓ ' in line or line.startswith('✓'):
                html_content.append('                <div class="positive-finding">\n')
                content = self.convert_inline_markdown(line.replace('✓ ', ''))
                html_content.append(f'                    {content}\n')
                html_content.append('                </div>\n')
                i += 1
                continue
            
            if '⚠️' in line or 'WARNING' in line.upper() or 'DISCLAIMER' in line:
                html_content.append('                <div class="warning-box">\n')
                content = self.convert_inline_markdown(line)
                html_content.append(f'                    {content}\n')
                html_content.append('                </div>\n')
                i += 1
                continue
            
            # Regular paragraph
            if line:
                para_html = self.convert_inline_markdown(line)
                html_content.append(f'                <p>{para_html}</p>\n')
            
            i += 1
        
        # Close last section
        if current_section:
            html_content.append('            </section>\n')
        
        return ''.join(html_content)


def extract_metadata(markdown_text):
    """Extract metadata from markdown for template."""
    metadata = {
        'title': 'C/C++ Code Review Report',
        'subtitle': 'Code Review Analysis',
        'timestamp': datetime.now().strftime('%B %d, %Y'),
        'footer': ''
    }
    
    lines = markdown_text.split('\n')
    for i, line in enumerate(lines):
        if 'Generation Time' in line and i + 1 < len(lines):
            metadata['timestamp'] = line.split(':', 1)[1].strip()
        if 'Tool:' in line:
            # Extract footer information
            footer_lines = []
            j = i
            while j < len(lines) and j < i + 10:
                if lines[j].strip().startswith('-') and 'Tool' in lines[j]:
                    break
                if lines[j].strip() and not lines[j].startswith('#'):
                    footer_lines.append(f'<p>{lines[j].strip()}</p>')
                j += 1
            metadata['footer'] = '\n            '.join(footer_lines)
    
    return metadata


def main():
    """Main conversion function."""
    # Parse command line arguments
    if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'copilot-cpp-review-report.md'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'copilot-cpp-review-report.html'
    
    input_path = Path(input_file)
    output_path = Path(output_file)
    
    # Check if input file exists
    if not input_path.exists():
        print(f"❌ Error: Input file '{input_file}' not found!")
        sys.exit(1)
    
    print(f"📖 Reading markdown from: {input_path}")
    
    # Read markdown content
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)
    
    # Extract metadata
    print("🔍 Extracting metadata...")
    metadata = extract_metadata(markdown_content)
    
    # Convert markdown to HTML
    print("🔄 Converting markdown to HTML...")
    converter = MarkdownToHTMLConverter()
    html_content = converter.convert_to_html(markdown_content)
    
    # Generate final HTML
    print("🎨 Applying styling and generating final HTML...")
    final_html = HTML_TEMPLATE.format(
        title=metadata['title'],
        subtitle=metadata['subtitle'],
        timestamp=metadata['timestamp'],
        content=html_content,
        footer=metadata['footer'] if metadata['footer'] else '<p>Generated by Python Markdown Converter</p>'
    )
    
    # Write to output file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_html)
        print(f"✅ Success! HTML report generated: {output_path}")
        print(f"📊 File size: {output_path.stat().st_size:,} bytes")
        print(f"\n💡 You can now open '{output_path}' in your browser!")
    except Exception as e:
        print(f"❌ Error writing file: {e}")
        sys.exit(1)


if __name__ == '__main__':
    print("=" * 70)
    print("  C/C++ Code Review Report - Markdown to HTML Converter")
    print("=" * 70)
    print()
    main()
    print()
    print("=" * 70)
