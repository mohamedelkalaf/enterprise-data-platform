import json
from superset.app import create_app

app = create_app()

with app.app_context():
    from superset.extensions import db
    from superset.models.core import Database
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.slice import Slice
    from superset.models.dashboard import Dashboard

    print("--- Updating Executive V2 Dashboard Charts inside Apache Superset ---")

    database = db.session.query(Database).filter_by(database_name="EDP_Gold_DataWarehouse").first()
    dataset = db.session.query(SqlaTable).filter_by(
        table_name="fact_sales_summary",
        schema="gold",
        database_id=database.id
    ).first()

    dataset.fetch_metadata()
    for col in dataset.columns:
        if col.column_name == "created_at":
            col.is_dttm = True
    db.session.commit()

    def upsert_chart(slice_name, viz_type, params_dict):
        chart = db.session.query(Slice).filter_by(slice_name=slice_name).first()
        if not chart:
            chart = Slice(slice_name=slice_name)
            db.session.add(chart)
        chart.datasource_id = dataset.id
        chart.datasource_type = "table"
        chart.viz_type = viz_type
        chart.params = json.dumps(params_dict)
        chart.query_context = None
        db.session.commit()
        return chart

    # Row 1: 4 KPI Cards
    kpi_1 = upsert_chart("Gross Sales Revenue (EGP)", "big_number_total", {
        "datasource": f"{dataset.id}__table", "viz_type": "big_number_total",
        "metric": {"expressionType": "SIMPLE", "column": {"column_name": "total_amount", "type": "NUMERIC"}, "aggregate": "SUM", "label": "Gross Sales"},
        "subheader": "Total Invoiced Volume", "y_axis_format": ",.0f", "header_font_size": 0.32, "subheader_font_size": 0.14
    })

    kpi_2 = upsert_chart("Total Cash Collected (EGP)", "big_number_total", {
        "datasource": f"{dataset.id}__table", "viz_type": "big_number_total",
        "metric": {"expressionType": "SIMPLE", "column": {"column_name": "paid_amount", "type": "NUMERIC"}, "aggregate": "SUM", "label": "Collected Cash"},
        "subheader": "Actual Settled Cash", "y_axis_format": ",.0f", "header_font_size": 0.32, "subheader_font_size": 0.14
    })

    kpi_3 = upsert_chart("Outstanding AR Balance (EGP)", "big_number_total", {
        "datasource": f"{dataset.id}__table", "viz_type": "big_number_total",
        "metric": {"expressionType": "SIMPLE", "column": {"column_name": "balance_due", "type": "NUMERIC"}, "aggregate": "SUM", "label": "AR Balance Due"},
        "subheader": "Pending Receivables", "y_axis_format": ",.0f", "header_font_size": 0.32, "subheader_font_size": 0.14
    })

    kpi_4 = upsert_chart("Total Processed Orders", "big_number_total", {
        "datasource": f"{dataset.id}__table", "viz_type": "big_number_total",
        "metric": {"expressionType": "SIMPLE", "column": {"column_name": "order_id", "type": "VARCHAR"}, "aggregate": "COUNT", "label": "Orders Count"},
        "subheader": "Enterprise Transactions", "y_axis_format": ",d", "header_font_size": 0.32, "subheader_font_size": 0.14
    })

    # Row 2: Order Status & Invoice Status Donuts
    chart_donut = upsert_chart("Revenue Share by Order Status", "pie", {
        "datasource": f"{dataset.id}__table", "viz_type": "pie",
        "groupby": ["order_status"],
        "metric": {"expressionType": "SIMPLE", "column": {"column_name": "total_amount", "type": "NUMERIC"}, "aggregate": "SUM", "label": "Revenue"},
        "adhoc_filters": [], "show_labels": True, "donut": True, "show_legend": True, "color_scheme": "supersetColors"
    })

    chart_inv_donut = upsert_chart("Collections by Invoice Status", "pie", {
        "datasource": f"{dataset.id}__table", "viz_type": "pie",
        "groupby": ["invoice_status"],
        "metric": {"expressionType": "SIMPLE", "column": {"column_name": "total_amount", "type": "NUMERIC"}, "aggregate": "SUM", "label": "Volume"},
        "adhoc_filters": [], "show_labels": True, "donut": True, "show_legend": True, "color_scheme": "d3Category10"
    })

    # Row 3: Top 10 Corporate Clients Bar Chart (ECharts v4)
    chart_top_cust = upsert_chart("Top 10 Corporate Clients by Revenue", "echarts_timeseries_bar", {
        "datasource": f"{dataset.id}__table",
        "viz_type": "echarts_timeseries_bar",
        "x_axis": "customer_name",
        "groupby": [],
        "metrics": [
            {"expressionType": "SIMPLE", "column": {"column_name": "total_amount", "type": "NUMERIC"}, "aggregate": "SUM", "label": "Total Sales (EGP)"},
            {"expressionType": "SIMPLE", "column": {"column_name": "paid_amount", "type": "NUMERIC"}, "aggregate": "SUM", "label": "Paid Cash (EGP)"},
            {"expressionType": "SIMPLE", "column": {"column_name": "balance_due", "type": "NUMERIC"}, "aggregate": "SUM", "label": "Balance Due (EGP)"}
        ],
        "adhoc_filters": [],
        "row_limit": 10,
        "order_desc": True,
        "show_legend": True,
        "y_axis_format": ",.0f",
        "color_scheme": "supersetColors"
    })

    # Row 4: Detailed Ledger Table
    chart_table = upsert_chart("Executive Sales & Billing Ledger (Live DW)", "table", {
        "datasource": f"{dataset.id}__table", "viz_type": "table",
        "query_mode": "raw",
        "all_columns": [
            "order_number", "customer_name", "order_status",
            "total_amount", "invoice_number", "invoice_status",
            "paid_amount", "balance_due", "currency", "created_at"
        ],
        "adhoc_filters": [], "row_limit": 500, "page_length": 10
    })

    dash_slug = "edp-executive-dashboard"
    dash = db.session.query(Dashboard).filter_by(slug=dash_slug).first()
    dash.slices = [kpi_1, kpi_2, kpi_3, kpi_4, chart_donut, chart_inv_donut, chart_top_cust, chart_table]
    db.session.commit()
    print("[SUPERSET CHART FIXED] Top 10 Corporate Clients Bar Chart is now updated to echarts_timeseries_bar!")
