from core.errors import ProjectAccessDeniedError


def require_project_access(project_id: int, unlocked_project_ids: set[int] | list[int]) -> None:
    if project_id not in set(unlocked_project_ids):
        raise ProjectAccessDeniedError("当前会话无权访问该项目。")

