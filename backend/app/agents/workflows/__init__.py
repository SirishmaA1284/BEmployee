from app.agents.workflows.customer import (  # noqa: F401
    build_search_customers_workflow,
    build_search_products_workflow,
)
from app.agents.workflows.finance import build_sales_report_workflow  # noqa: F401
from app.agents.workflows.inventory import (  # noqa: F401
    build_check_inventory_workflow,
    build_low_stock_workflow,
)
from app.agents.workflows.order import build_order_workflow  # noqa: F401
from app.agents.workflows.procurement import (  # noqa: F401
    build_compare_suppliers_workflow,
    build_create_purchase_order_workflow,
)