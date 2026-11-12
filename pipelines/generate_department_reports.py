import os
import sys
import psycopg2
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", 5435))
PG_USER = "postgres"
PG_PASS = "edp_password_2026"
DW_DB = "edp_dw"

REPORTS_DIR = os.getenv("REPORTS_DIR", "reports_output")
os.makedirs(REPORTS_DIR, exist_ok=True)

def fetch_gold_sales():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=DW_DB)
    cur = conn.cursor()
    cur.execute("SELECT order_number, customer_name, order_status, total_amount, invoice_number, invoice_status, paid_amount, balance_due, currency FROM gold.fact_sales_summary ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def build_pdf_report(filename, dept_title, headers, data_rows, summary_text):
    filepath = os.path.join(REPORTS_DIR, filename)
    doc = SimpleDocTemplate(filepath, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"<b>ENTERPRISE DATA PLATFORM - OFFICIAL REPORT</b>", styles['Title']))
    elements.append(Paragraph(f"<b>Department:</b> {dept_title}", styles['Heading2']))
    elements.append(Paragraph(f"<b>Generated At:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Spacer(1, 15))

    table_data = [headers] + data_rows
    t = Table(table_data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1f4e78")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f2f4f8")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))
    elements.append(Paragraph(f"<b>Executive Summary:</b> {summary_text}", styles['Normal']))
    elements.append(Spacer(1, 25))
    elements.append(Paragraph("Authorized Signature: _______________________", styles['Normal']))

    doc.build(elements)
    print(f"[REPORT GENERATED] {dept_title} -> {filepath}")
    return filepath

def run_reporting_engine(auto_print=False):
    print("--- Starting Enterprise Departmental Report Engine ---")
    rows = fetch_gold_sales()

    # 1. Sales Department Report
    sales_headers = ["Order #", "Customer", "Order Status", "Total Amount", "Currency"]
    sales_data = [[r[0], r[1], r[2], f"{r[3]:,.2f}", r[8]] for r in rows[:100]]
    total_rev = sum(float(r[3]) for r in rows)
    sales_pdf = build_pdf_report(
        "Sales_Department_Report.pdf",
        "Sales & Commercial Operations Department",
        sales_headers,
        sales_data,
        f"Total Orders Processed: {len(rows)} | Total Gross Sales Volume: {total_rev:,.2f} EGP"
    )

    # 2. Finance & Billing Department Report
    fin_headers = ["Invoice #", "Order #", "Invoice Status", "Paid Amount", "Balance Due", "Currency"]
    fin_data = [[r[4], r[0], r[5], f"{r[6]:,.2f}", f"{r[7]:,.2f}", r[8]] for r in rows[:100]]
    total_paid = sum(float(r[6]) for r in rows)
    total_due = sum(float(r[7]) for r in rows)
    fin_pdf = build_pdf_report(
        "Finance_Billing_Report.pdf",
        "Finance, Billing & Accounts Receivable Department",
        fin_headers,
        fin_data,
        f"Total Collected Cash: {total_paid:,.2f} EGP | Total Outstanding AR Balance: {total_due:,.2f} EGP"
    )

    if auto_print and sys.platform == "win32":
        for pdf_file in [sales_pdf, fin_pdf]:
            try:
                print(f"[PRINTER SPOOLER] Sending {pdf_file} to default physical printer...")
                os.startfile(os.path.abspath(pdf_file), "print")
            except Exception as e:
                print(f"[PRINTER WARNING] Could not auto-print {pdf_file}: {e}")

if __name__ == "__main__":
    should_print = "--print" in sys.argv
    run_reporting_engine(auto_print=should_print)
