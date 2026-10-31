"""Convert UI labels only; business evidence and input values stay unchanged."""

from functools import wraps

LANGUAGES = ["简体中文", "English", "Deutsch"]

# UI text only. Never translate stored records, source excerpts or identifiers.
TEXT = {
    "使用教学": ("User guide", "Anleitung"),
    "了解六个板块，按步骤完成业务处理。": (
        "Learn the six sections and complete your work step by step.",
        "Die sechs Bereiche kennenlernen und Aufgaben Schritt für Schritt erledigen.",
    ),
    "总览": ("Overview", "Übersicht"),
    "项目首页": ("Projects", "Projekte"),
    "报价决策": ("Supplier quotes", "Lieferantenangebote"),
    "任务与日报": ("Tasks & daily reports", "Aufgaben & Tagesberichte"),
    "差评改进": ("Customer feedback", "Kundenfeedback"),
    "本地化与校验": ("Content & checks", "Inhalte & Prüfung"),
    "设置": ("Settings", "Einstellungen"),
    "AI 文档理解": ("AI document understanding", "KI-Dokumentenanalyse"),
    "使用偏好": ("Preferences", "Präferenzen"),
    "选择界面语言和本次使用的 AI 服务。": (
        "Choose your interface language and AI service.",
        "Wählen Sie die Anzeigesprache und den KI-Dienst.",
    ),
    "界面语言": ("Interface language", "Anzeigesprache"),
    "显示语言": ("Language", "Sprache"),
    "AI 服务": ("AI service", "KI-Dienst"),
    "服务商": ("Provider", "Anbieter"),
    "接口地址": ("API base URL", "API-Basis-URL"),
    "模型名称": ("Model name", "Modellname"),
    "该服务商的 API 密钥": ("API key for this provider", "API-Schlüssel dieses Anbieters"),
    "应用设置": ("Apply settings", "Einstellungen anwenden"),
    "恢复本机配置并清除会话密钥": (
        "Use local configuration and clear session keys",
        "Lokale Konfiguration verwenden und Sitzungsschlüssel löschen",
    ),
    "当前使用：本机环境配置。": (
        "Using the local environment configuration.",
        "Lokale Umgebungskonfiguration aktiv.",
    ),
    "切换界面提示和表单标题；评价原文、商品文案和已保存记录保持原语言。": (
        "Changes interface labels. Reviews, product copy and saved records "
        "keep their original language.",
        "Ändert die Oberflächentexte. Bewertungen, Produkttexte und "
        "gespeicherte Daten bleiben unverändert.",
    ),
    "配置只对当前浏览器会话生效，不修改本机 .env，也不影响其他人的设置。": (
        "Settings apply to this browser session only. The local .env and "
        "other users are unchanged.",
        "Die Einstellungen gelten nur für diese Sitzung. Die lokale .env "
        "und andere Nutzer bleiben unverändert.",
    ),
    "模型和接口地址请从所选服务商控制台复制；不同地区、账户可能使用不同地址。": (
        "Copy the model name and API URL from your provider console; they "
        "may vary by account or region.",
        "Kopieren Sie Modellname und API-URL aus der Anbieter-Konsole; "
        "Konto und Region können abweichen.",
    ),
    "输入框不会回显已保存密钥。切换服务商需要填写对应密钥，不会复用其他厂商密钥。": (
        "Saved keys are not shown. Each provider requires its own key.",
        "Gespeicherte Schlüssel werden nicht angezeigt. Jeder Anbieter "
        "benötigt einen eigenen Schlüssel.",
    ),
    "已应用。下一次 AI 分析将使用此服务；保存设置不会发起付费请求。": (
        "Applied for the next AI analysis. Saving does not send an API request.",
        "Für die nächste KI-Analyse übernommen. Speichern sendet keine API-Anfrage.",
    ),
    "服务商入口已提供；除 DeepSeek 外，其他服务仍需用你有权限的模型进行兼容性验证。": (
        "Only DeepSeek has been live-tested. Validate other providers with "
        "a model available to your account.",
        "Nur DeepSeek wurde online getestet. Prüfen Sie andere Anbieter mit "
        "einem verfügbaren Modell.",
    ),
    "客户评价与改进": ("Customer feedback & improvements", "Kundenfeedback & Verbesserungen"),
    "请先进入一个项目。": ("Open a project first.", "Öffnen Sie zuerst ein Projekt."),
    "当前工作区": ("Workspace", "Arbeitsbereich"),
    "本地演示用户": ("Demo user", "Demo-Nutzer"),
    "项目负责人": ("Project owner", "Projektleitung"),
    "采购": ("Procurement", "Einkauf"),
    "运营": ("Operations", "Betrieb"),
    "品控": ("Quality control", "Qualitätskontrolle"),
    "评价文件": ("Review file", "Bewertungsdatei"),
    "批次名称": ("Batch name", "Chargenname"),
    "校验并导入": ("Validate and import", "Prüfen und importieren"),
    "下载评价 CSV 示例": ("Download sample CSV", "CSV-Beispiel herunterladen"),
    "分类方式": ("Analysis method", "Analysemethode"),
    "规则分类": ("Rule-based analysis", "Regelbasierte Analyse"),
    "真实 AI 分类": ("AI analysis", "KI-Analyse"),
    "运行所选分类": ("Analyze reviews", "Bewertungen analysieren"),
    "待你确认": ("Needs your review", "Bitte prüfen"),
    "已确认": ("Confirmed", "Bestätigt"),
    "已修改确认": ("Revised and confirmed", "Überarbeitet und bestätigt"),
    "已忽略": ("Dismissed", "Verworfen"),
    "审核备注": ("Review notes", "Prüfnotizen"),
    "接受": ("Confirm", "Bestätigen"),
    "修改并接受": ("Revise and confirm", "Überarbeiten und bestätigen"),
    "驳回": ("Dismiss", "Verwerfen"),
    "支持证据": ("Source evidence", "Originalbelege"),
    "生成改进任务草稿": ("Draft improvement task", "Verbesserungsaufgabe entwerfen"),
    "确认并发布改进任务": ("Confirm and publish task", "Aufgabe bestätigen und veröffentlichen"),
    "比较两批评价": ("Compare review batches", "Bewertungsgruppen vergleichen"),
    "分析记录（需要时查看）": ("Analysis details (optional)", "Analysedetails (optional)"),
    "任务执行": ("Task execution", "Aufgaben bearbeiten"),
    "提交日报": ("Submit daily report", "Tagesbericht einreichen"),
    "风险复盘": ("Progress review", "Fortschritt prüfen"),
    "更新状态": ("Update status", "Status aktualisieren"),
    "待验收交付": ("Deliveries awaiting review", "Lieferergebnisse zur Prüfung"),
    "目标市场": ("Target market", "Zielmarkt"),
    "美国英语": ("US English", "US-Englisch"),
    "德国德语": ("German", "Deutsch"),
    "文案与修改记录": ("Copy & revisions", "Texte & Überarbeitungen"),
    "独立规则校验": ("Rule checks", "Regelprüfung"),
    "运行规则检查": ("Run checks", "Prüfung starten"),
    "待检查文本": ("Text to check", "Zu prüfender Text"),
    "业务场景": ("Business scenario", "Geschäftsszenario"),
    "市场": ("Market", "Markt"),
    "保存人工 V1": ("Save manual V1", "Manuelle V1 speichern"),
    "修改反馈": ("Revision feedback", "Änderungswünsche"),
    "保存反馈和人工 V2": ("Save feedback and manual V2", "Feedback und manuelle V2 speichern"),
}


def translate(text: str, language: str | None = None) -> str:
    if language is None:
        import streamlit as st

        language = st.session_state.get("display_language", "简体中文")
    if language not in {"English", "Deutsch"}:
        return text
    index = 0 if language == "English" else 1
    # Longest matches first also supports existing HTML page headers.
    for source in sorted(TEXT, key=len, reverse=True):
        text = text.replace(source, TEXT[source][index])
    return text


def enable_display_language() -> None:
    import streamlit as st
    from streamlit.delta_generator import DeltaGenerator

    for name in (
        "markdown",
        "caption",
        "info",
        "warning",
        "error",
        "success",
        "title",
        "header",
        "subheader",
        "button",
        "text_input",
        "text_area",
        "selectbox",
        "radio",
        "expander",
        "checkbox",
        "form_submit_button",
    ):
        original = getattr(DeltaGenerator, name)
        if getattr(original, "_tradeloop_language", False):
            continue

        def wrap(method):
            @wraps(method)
            def translated(self, *args, **kwargs):

                if args and isinstance(args[0], str):
                    args = (translate(args[0]), *args[1:])
                return method(self, *args, **kwargs)

            translated._tradeloop_language = True
            return translated

        setattr(DeltaGenerator, name, wrap(original))
        setattr(st, name, getattr(st._main, name))
