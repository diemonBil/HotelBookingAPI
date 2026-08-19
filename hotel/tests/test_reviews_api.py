import pytest
from django.urls import reverse

from hotel.models import Review

pytestmark = pytest.mark.django_db

LIST_URL = reverse("review-list")


def detail_url(pk):
    return reverse("review-detail", args=[pk])


def test_reviews_are_publicly_readable(api_client, user, hotel):
    Review.objects.create(user=user, hotel=hotel, rating=5, comment="Lovely stay.")
    response = api_client.get(LIST_URL)
    assert response.status_code == 200
    assert response.data["count"] == 1


def test_anonymous_cannot_post_a_review(api_client, hotel):
    response = api_client.post(LIST_URL, {"hotel": hotel.id, "rating": 5, "comment": "Nice."})
    assert response.status_code == 401


def test_author_is_taken_from_the_request(auth_client, user, hotel):
    response = auth_client.post(
        LIST_URL, {"hotel": hotel.id, "rating": 4, "comment": "Good value."}
    )
    assert response.status_code == 201
    assert Review.objects.get().user == user


def test_rating_is_bounded(auth_client, hotel):
    response = auth_client.post(LIST_URL, {"hotel": hotel.id, "rating": 9, "comment": "?"})
    assert response.status_code == 400


def test_a_user_cannot_review_the_same_hotel_twice(auth_client, user, hotel):
    Review.objects.create(user=user, hotel=hotel, rating=5, comment="First.")
    response = auth_client.post(LIST_URL, {"hotel": hotel.id, "rating": 1, "comment": "Second."})
    assert response.status_code == 400


def test_author_can_edit_their_own_review(auth_client, user, hotel):
    review = Review.objects.create(user=user, hotel=hotel, rating=3, comment="Okay.")
    response = auth_client.patch(detail_url(review.id), {"rating": 5})
    assert response.status_code == 200
    review.refresh_from_db()
    assert review.rating == 5


def test_others_cannot_edit_a_review(api_client, other_user, user, hotel):
    """Regression: any authenticated user could edit or delete any review."""
    review = Review.objects.create(user=user, hotel=hotel, rating=3, comment="Okay.")
    api_client.force_authenticate(user=other_user)

    assert api_client.patch(detail_url(review.id), {"rating": 1}).status_code == 403
    assert api_client.delete(detail_url(review.id)).status_code == 403
    review.refresh_from_db()
    assert review.rating == 3


def test_author_can_delete_their_own_review(auth_client, user, hotel):
    review = Review.objects.create(user=user, hotel=hotel, rating=3, comment="Okay.")
    assert auth_client.delete(detail_url(review.id)).status_code == 204
    assert not Review.objects.exists()


def test_staff_can_moderate_any_review(staff_client, user, hotel):
    review = Review.objects.create(user=user, hotel=hotel, rating=1, comment="Spam.")
    assert staff_client.delete(detail_url(review.id)).status_code == 204
