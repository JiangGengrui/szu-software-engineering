"""Idempotent fictional data. Existing accounts, passwords and edited works are untouched."""
import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import select

from .auth import hash_password, validate_password
from .common import BusinessError, fail, now, today, transaction
from .models import User, Work, db
from .work import replace_tags


def init_demo() -> None:
    with transaction(write=True):
        admins = list(db.session.scalars(select(User).where(User.role == "admin")))
        if len(admins) > 1:
            fail(1005, "已有多个管理员，初始化不会修改现有账号")
        students: list[User] = []
        for name, role, status in (("admin", "admin", "active"), ("student_a", "user", "active"),
                                   ("student_b", "user", "active"), ("student_c", "user", "disabled")):
            if role == "admin" and admins:
                continue
            user = db.session.scalar(select(User).where(User.username == name))
            if user is None:
                key = "SEED_ADMIN_PASSWORD" if role == "admin" else "SEED_USER_PASSWORD"
                password = current_app.config.get(key)
                if not isinstance(password, str):
                    fail(1001, f"请通过{key}配置初始化密码")
                validate_password(password)
                user = User(username=name, password_hash=hash_password(password), role=role,
                            status=status, created_at=now())
                db.session.add(user)
                db.session.flush()
            elif user.role != role:
                fail(1005, "种子用户名已被不同角色占用，初始化不会覆盖")
            if role == "user":
                students.append(user)
        titles = ["秋日校运会", "图书馆的午后", "社团招新记录", "校园志愿活动", "演示：已移除的活动"]
        for index, title in enumerate(titles):
            key = f"demo-work-{index + 1}"
            if db.session.scalar(select(Work.id).where(Work.seed_key == key)) is not None:
                continue
            author = students[2] if index == 4 else students[index % 2]
            work = Work(user_id=author.id, seed_key=key, title=title,
                        content=f"{title}。这是校园影集的虚构演示作品，用于体验发布、检索与互动。",
                        activity_date=today(), status="visible" if author.status == "active" else "removed",
                        created_at=now(), updated_at=now())
            db.session.add(work)
            db.session.flush()
            replace_tags(work, ["演示", "校运会"] if index == 0 else ["演示"])


@click.command("init-demo")
@with_appcontext
def init_demo_command() -> None:
    try:
        init_demo()
    except BusinessError as error:
        raise click.ClickException(error.message) from None
    click.echo("演示数据初始化完成；已有账号、密码和作品保持不变。")
