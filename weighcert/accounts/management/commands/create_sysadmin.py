"""
Management command: create_sysadmin
Usage:
    py -3 manage.py create_sysadmin
    py -3 manage.py create_sysadmin --username sysadmin --password WeighCert@2026 --reset

Creates (or resets the password of) the one-and-only System Administrator account.
Only ONE sysadmin can exist in the system at any time.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction


class Command(BaseCommand):
    help = "Create or reset the unique System Administrator account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username", default="sysadmin",
            help="Username for the System Administrator (default: sysadmin)"
        )
        parser.add_argument(
            "--password", default="SysAdmin@123456",
            help="Password / master key (default: SysAdmin@123456)"
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="If the sysadmin already exists, reset their password instead of erroring"
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        do_reset = options["reset"]

        # Check if a sysadmin already exists
        from accounts.models import Profile
        existing = Profile.objects.filter(role="sysadmin").first()

        if existing:
            if do_reset:
                existing.user.set_password(password)
                existing.user.save()
                existing.must_change_password = False
                existing.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✔ Sysadmin password reset for '{existing.user.username}'."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠ A System Administrator already exists: '{existing.user.username}'. "
                        f"Use --reset to reset the password."
                    )
                )
            return

        with transaction.atomic():
            if User.objects.filter(username=username).exists():
                self.stderr.write(
                    self.style.ERROR(
                        f"Username '{username}' is already taken by a non-sysadmin user. "
                        f"Choose a different username with --username."
                    )
                )
                return

            user = User.objects.create_user(
                username=username,
                password=password,
                first_name="System",
                last_name="Administrator",
                is_staff=True,       # Optional: grants Django /django-admin/ access too
                is_superuser=False,  # We control permissions via our own role system
            )
            profile = user.profile
            profile.role                = "sysadmin"
            profile.designation         = "System Administrator"
            profile.must_change_password = False
            profile.is_active           = True
            profile.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✔ System Administrator created!\n"
                f"  Username : {username}\n"
                f"  Password : {password}\n"
                f"  Role     : sysadmin\n\n"
                f"  → Login at http://127.0.0.1:8000/login/\n"
                f"  → Panel   http://127.0.0.1:8000/sysadmin/\n\n"
                f"  ⚠ Change this password immediately after first login!\n"
            )
        )
