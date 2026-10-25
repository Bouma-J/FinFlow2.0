import django
django.setup()

from django.conf import settings
from apps.accounts.models import User
from apps.accounts.password_services import (
    generate_temporary_password,
    issue_temporary_password,
)

pwd = generate_temporary_password()
assert len(pwd) >= 12
u2 = User(username="tmp_pwd_test_user", email="tmp@example.com")
u2.set_unusable_password()
u2.save()
raw, sent = issue_temporary_password(u2, reason="created", send_email=False)
assert u2.must_change_password is True
assert u2.check_password(raw)
assert sent is False
u2.delete()
print("OK", settings.EMAIL_BACKEND)
