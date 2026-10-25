import json
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from core.db import init_db
from core.schemas import ProjectCreate
from core.ui import render_sidebar
from services.imports import import_quotes, list_quote_artifacts
from services.project_service import (
    ProjectNameExistsError,
    create_project,
    get_project_by_name,
    list_projects,
)

init_db()
DEMO_FILE = Path(__file__).resolve().parents[1] / "data" / "demo" / "supplier_quotes.csv"

st.set_page_config(page_title="项目首页 · TradeLoop", page_icon="🏠", layout="wide")
st.title("项目首页")
st.caption("创建项目、选择目标市场，并通过演示身份查看同一项目事实。")

render_sidebar(require_unlock=True)

left, right = st.columns(2)

with left:
    st.subheader("创建项目")
    with st.form("create_project_form", clear_on_submit=True):
        name = st.text_input("项目名称", placeholder="例如：秋季新品出海")
        product_name = st.text_input("产品名称", placeholder="例如：真空保温杯")
        markets = st.multiselect(
            "目标市场",
            options=["US", "DE"],
            default=["US", "DE"],
            format_func=lambda item: {"US": "美国", "DE": "德国"}[item],
        )
        access_code = st.text_input("项目访问码", type="password", help="至少 4 位，只保存哈希。")
        submitted = st.form_submit_button("创建项目", use_container_width=True)

    if submitted:
        try:
            payload = ProjectCreate(
                name=name,
                product_name=product_name,
                access_code=access_code,
                markets=markets,
            )
            project = create_project(payload)
            unlocked = set(st.session_state.get("unlocked_project_ids", []))
            unlocked.add(project.id)
            st.session_state["unlocked_project_ids"] = list(unlocked)
            st.session_state["active_project_id"] = project.id
            st.success(f"项目“{project.name}”已创建。")
            st.rerun()
        except ValidationError as exc:
            for issue in exc.errors():
                st.error(f"{issue['loc'][0]}：{issue['msg']}")
        except ProjectNameExistsError as exc:
            st.error(str(exc))

with right:
    st.subheader("一键加载演示项目")
    st.write("将创建保温杯新品项目，并导入 3 家供应商的标准报价。")
    st.code("演示访问码：demo2026", language=None)
    if st.button("加载演示项目", type="primary", use_container_width=True):
        project = get_project_by_name("保温杯新品出海")
        if project is None:
            project = create_project(
                ProjectCreate(
                    name="保温杯新品出海",
                    product_name="真空保温杯 750ml",
                    access_code="demo2026",
                    markets=["US", "DE"],
                )
            )
        if not list_quote_artifacts(project.id):
            import_quotes(project.id, DEMO_FILE, "首轮供应商报价")
        unlocked = set(st.session_state.get("unlocked_project_ids", []))
        unlocked.add(project.id)
        st.session_state["unlocked_project_ids"] = list(unlocked)
        st.session_state["active_project_id"] = project.id
        st.success("演示项目已就绪，请进入“报价决策”。")
        st.rerun()

st.divider()
projects = list_projects()
if projects:
    st.subheader("已有项目")
    table = [
        {
            "ID": project.id,
            "项目": project.name,
            "产品": project.product_name,
            "目标市场": ", ".join(json.loads(project.markets_json)),
            "创建时间": project.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for project in projects
    ]
    st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
else:
    st.info("尚无项目。你可以创建一个新项目，或加载演示项目。")

st.caption("访问码仅用于黑客松演示级项目隔离，不代表成熟的企业权限系统。")

