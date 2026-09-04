from marshmallow import Schema, fields

class PortfolioSummarySchema(Schema):
    total_active_loans = fields.Int()
    gross_loan_portfolio = fields.Float()
    portfolio_at_risk_30 = fields.Float()
    collection_rate = fields.Float()

class DashboardSeriesDataSchema(Schema):
    label = fields.String()
    value = fields.Float()

class DashboardFeedSchema(Schema):
    # e.g., [{"label": "Jan", "value": 1000}, {"label": "Feb", "value": 1500}]
    disbursements_over_time = fields.List(fields.Nested(DashboardSeriesDataSchema))
    collections_over_time = fields.List(fields.Nested(DashboardSeriesDataSchema))
    portfolio_status_distribution = fields.List(fields.Nested(DashboardSeriesDataSchema))

class CustomerDashboardFeedSchema(Schema):
    total_borrowed = fields.Float()
    total_repaid = fields.Float()
    current_outstanding = fields.Float()
    loan_history_summary = fields.List(fields.Nested(DashboardSeriesDataSchema))
