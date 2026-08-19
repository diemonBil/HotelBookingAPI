from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "username", "email", "password", "first_name", "last_name", "is_staff")
        read_only_fields = ("id", "is_staff")
        extra_kwargs = {
            "password": {
                "write_only": True,
                "style": {"input_type": "password"},
            },
            "email": {"required": True},
        }

    def validate_password(self, value):
        # Runs the AUTH_PASSWORD_VALIDATORS chain, which the previous
        # min_length=5 rule bypassed entirely.
        validate_password(value)
        return value

    def create(self, validated_data):
        """Create a user with a hashed password."""
        return get_user_model().objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        """Update a user, re-hashing the password when one is supplied."""
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user
