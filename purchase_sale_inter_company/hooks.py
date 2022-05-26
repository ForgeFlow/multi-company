import logging

_logger = logging.getLogger(__name__)


def pre_init_hook(cr):
    _logger.info("Create column in database")
    cr.execute("""
        ALTER TABLE res_company ADD COLUMN IF NOT EXISTS intercompany_overwrite_purchase_price boolean;
    """)
