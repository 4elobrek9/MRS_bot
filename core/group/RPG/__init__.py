# Import shared resources first
from .MAINrpg import rpg_router, setup_rpg_handlers, initialize_on_startup
from .item import ItemSystem
from .rpg_utils import ensure_db_initialized

# Import feature modules
from .inventory import show_inventory, get_user_lumcoins, get_user_inventory_db, remove_item_from_inventory
from .market import show_shop_main, show_market
from .crafttable import show_workbench_cmd
from .trade import start_trade
from .investment import show_investment, show_my_investments
from .auction import show_auction

__all__ = [
    # Core functionality
    'rpg_router',
    'setup_rpg_handlers',
    'initialize_on_startup',
    'ensure_db_initialized',
    'ItemSystem',
    
    # Feature handlers
    'show_inventory',
    'show_workbench_cmd',
    'show_shop_main',
    'show_market',
    'start_trade',
    'show_auction',
    'show_investment',
    'show_my_investments',
    
    # Utility functions
    'get_user_lumcoins',
    'get_user_inventory_db',
    'remove_item_from_inventory'
]