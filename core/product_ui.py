"""One explicit product selection shared by the existing business pages."""

import streamlit as st

from core.errors import TradeLoopError
from services.product_identity_service import create_product, list_products


def select_product(project_id, token, *, owner=False):
    products = list_products(project_id=project_id, session_token=token)
    if owner:
        with st.expander("登记产品（使用明确业务编号，不自动按名称匹配）"):
            key = st.text_input("产品业务编号", key=f"new_product_key_{project_id}")
            name = st.text_input("产品名称", key=f"new_product_name_{project_id}")
            if st.button("登记产品", key=f"create_product_{project_id}"):
                try:
                    product = create_product(
                        project_id=project_id,
                        session_token=token,
                        external_key=key,
                        display_name=name,
                    )
                except (TradeLoopError, ValueError) as exc:
                    st.error(f"产品登记失败：{exc}")
                else:
                    is_existing = any(item.id == product.id for item in products)
                    if is_existing:
                        st.info(
                            f"产品已存在，已复用产品：{product.display_name} · ID {product.id}。"
                        )
                    else:
                        st.success(f"产品登记成功：{product.display_name} · ID {product.id}。")
                    products = list_products(project_id=project_id, session_token=token)
    labels = {p.id: f"{p.display_name} · {p.external_key} · ID {p.id}" for p in products}
    if not labels:
        st.info("尚未登记产品。负责人可使用明确业务编号登记；不会自动猜测历史数据归属。")
        return None
    return st.selectbox(
        "当前产品", list(labels), format_func=labels.get, key=f"selected_product_{project_id}"
    )
