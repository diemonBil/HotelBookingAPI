/* Demo client for the Hotel Booking API: hash routing, no build step.
 * Depends on the global defined in api.js. */
(function (window, document) {
  "use strict";

  var Api = window.Api;
  var view = document.getElementById("view");
  var nav = document.getElementById("nav");
  var toasts = document.getElementById("toasts");

  var state = { user: null };

  /* ------------------------------------------------------------------ utils */

  function esc(value) {
    return String(value === null || value === undefined ? "" : value).replace(
      /[&<>"']/g,
      function (ch) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
      }
    );
  }

  function money(amount) {
    var value = Number(amount);
    return isNaN(value) ? "—" : "₴" + value.toFixed(2).replace(/\.00$/, "");
  }

  function isoDate(offsetDays) {
    var date = new Date();
    date.setDate(date.getDate() + (offsetDays || 0));
    return date.toISOString().slice(0, 10);
  }

  /* The locale is pinned rather than taken from the browser: the rest of the
   * interface is in English, and a mixed-language date reads as a bug. */
  function prettyDate(iso) {
    var date = new Date(iso + "T00:00:00");
    return isNaN(date) ? iso : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }

  function plural(count, singular, pluralForm) {
    return count + " " + (Number(count) === 1 ? singular : pluralForm || singular + "s");
  }

  function nightsBetween(from, to) {
    var ms = new Date(to + "T00:00:00") - new Date(from + "T00:00:00");
    return Math.max(0, Math.round(ms / 86400000));
  }

  /* A stable pair of hues per hotel, so a hotel always looks like itself. */
  function coverStyle(id) {
    var hue = (Number(id) * 61) % 360;
    return (
      "--c1: hsl(" + hue + " 52% 46%); --c2: hsl(" + ((hue + 42) % 360) + " 58% 32%)"
    );
  }

  function initial(name) {
    return esc((name || "?").trim().charAt(0).toUpperCase());
  }

  function stars(rating) {
    var whole = Math.round(Number(rating) || 0);
    return "★★★★★".slice(0, whole) + "☆☆☆☆☆".slice(0, 5 - whole);
  }

  function toast(message, kind) {
    var node = document.createElement("div");
    node.className = "toast" + (kind === "bad" ? " toast--bad" : "");
    node.setAttribute("role", "status");
    node.textContent = message;
    toasts.appendChild(node);
    window.setTimeout(function () {
      node.remove();
    }, 5000);
  }

  function skeletons(count) {
    var items = [];
    for (var i = 0; i < count; i++) items.push('<div class="skeleton"></div>');
    return '<div class="grid">' + items.join("") + "</div>";
  }

  function empty(mark, title, hint) {
    return (
      '<div class="empty"><div class="empty__mark">' +
      mark +
      "</div><h3>" +
      esc(title) +
      "</h3><p>" +
      esc(hint || "") +
      "</p></div>"
    );
  }

  function form(id) {
    var values = {};
    var element = document.getElementById(id);
    new window.FormData(element).forEach(function (value, key) {
      values[key] = typeof value === "string" ? value.trim() : value;
    });
    return values;
  }

  /* Paint per-field validation returned by DRF next to the inputs. */
  function showErrors(scope, err) {
    scope.querySelectorAll("[data-error]").forEach(function (node) {
      node.remove();
    });
    var fields = err.fieldErrors();
    var handled = false;
    Object.keys(fields).forEach(function (name) {
      var input = scope.querySelector('[name="' + name + '"]');
      if (!input) return;
      var text = Array.isArray(fields[name]) ? fields[name].join(" ") : String(fields[name]);
      var note = document.createElement("p");
      note.className = "small notice notice--bad";
      note.setAttribute("data-error", "");
      note.textContent = text;
      input.parentNode.appendChild(note);
      handled = true;
    });
    if (!handled) toast(err.message, "bad");
  }

  /* ------------------------------------------------------------------- chrome */

  function renderNav() {
    var route = window.location.hash || "#/";
    var links = [{ href: "#/", label: "Stays" }];
    if (Api.isSignedIn()) links.push({ href: "#/bookings", label: "My bookings" });

    var html = links
      .map(function (link) {
        var current = route === link.href ? ' aria-current="page"' : "";
        return '<a class="navlink" href="' + link.href + '"' + current + ">" + link.label + "</a>";
      })
      .join("");

    html += '<a class="navlink" href="/api/v1/docs/">API docs</a>';

    if (state.user) {
      html +=
        '<span class="pill pill--brand">' +
        esc(state.user.username) +
        '</span><button class="btn btn--quiet" id="signout">Sign out</button>';
    } else if (!Api.isSignedIn()) {
      html += '<a class="btn btn--primary" href="#/login">Sign in</a>';
    }

    nav.innerHTML = html;
    var signout = document.getElementById("signout");
    if (signout) {
      signout.addEventListener("click", function () {
        Api.logout();
        state.user = null;
        toast("Signed out.");
        go("#/");
        renderNav();
      });
    }
  }

  function go(hash) {
    if (window.location.hash === hash) route();
    else window.location.hash = hash;
  }

  /* --------------------------------------------------------------- home view */

  var search = {
    q: "",
    check_in: isoDate(7),
    check_out: isoDate(9),
    adults: 2,
    children: 0
  };

  function renderHome() {
    view.innerHTML =
      '<section class="hero shell">' +
      "<h1>Find a room worth the trip.</h1>" +
      "<p>A demo storefront for the Hotel Booking API — real availability, real " +
      "overlap checks, and a booking that cannot be sold twice.</p>" +
      '<form class="searchbar" id="searchform">' +
      '<label class="field"><span>Where</span>' +
      '<input name="q" placeholder="City or hotel" value="' + esc(search.q) + '"></label>' +
      '<label class="field"><span>Check in</span>' +
      '<input type="date" name="check_in" value="' + esc(search.check_in) + '" min="' + isoDate(0) + '"></label>' +
      '<label class="field"><span>Check out</span>' +
      '<input type="date" name="check_out" value="' + esc(search.check_out) + '" min="' + isoDate(1) + '"></label>' +
      '<label class="field"><span>Guests</span>' +
      '<input type="number" name="adults" min="1" max="8" value="' + esc(search.adults) + '"></label>' +
      '<button class="btn btn--primary" type="submit">Search</button>' +
      "</form></section>" +
      '<section class="section shell">' +
      '<div class="section__head"><h2>Stays</h2><span class="muted small" id="count"></span></div>' +
      '<div id="results">' + skeletons(4) + "</div>" +
      "</section>";

    document.getElementById("searchform").addEventListener("submit", function (event) {
      event.preventDefault();
      var values = form("searchform");
      search.q = values.q;
      search.check_in = values.check_in;
      search.check_out = values.check_out;
      search.adults = Number(values.adults) || 1;
      loadHotels();
    });

    loadHotels();
  }

  function loadHotels() {
    var results = document.getElementById("results");
    Api.hotels({ search: search.q })
      .then(function (page) {
        document.getElementById("count").textContent = plural(page.count, "property", "properties");
        if (!page.results.length) {
          results.innerHTML = empty("🔍", "Nothing matches that search", "Try a different city.");
          return;
        }
        results.innerHTML =
          '<div class="grid">' +
          page.results
            .map(function (hotel) {
              var rating = hotel.average_rating
                ? '<span class="rating"><span class="stars">' +
                  stars(hotel.average_rating) +
                  "</span>" +
                  Number(hotel.average_rating).toFixed(1) +
                  '<span class="muted small">(' + hotel.review_count + ")</span></span>"
                : '<span class="muted small">No reviews yet</span>';
              return (
                '<a class="card hotelcard" href="#/hotels/' + hotel.id + '">' +
                '<div class="cover" style="' + coverStyle(hotel.id) + '">' +
                '<span class="cover__initial">' + initial(hotel.name) + "</span></div>" +
                '<div class="hotelcard__body"><h3>' + esc(hotel.name) + "</h3>" +
                '<p class="muted small">' + esc(hotel.location) + "</p>" +
                "<div>" + rating + "</div></div></a>"
              );
            })
            .join("") +
          "</div>";
      })
      .catch(function (err) {
        results.innerHTML = '<p class="notice notice--bad">' + esc(err.message) + "</p>";
      });
  }

  /* ------------------------------------------------------------- hotel detail */

  function renderHotel(id) {
    view.innerHTML = '<section class="section shell">' + skeletons(1) + "</section>";

    Promise.all([Api.hotel(id), Api.rooms({ hotel: id }), Api.reviews({ hotel: id })])
      .then(function (results) {
        drawHotel(results[0], results[1].results, results[2].results);
      })
      .catch(function (err) {
        view.innerHTML =
          '<section class="section shell"><p class="notice notice--bad">' +
          esc(err.message) +
          "</p></section>";
      });
  }

  function drawHotel(hotel, rooms, reviews) {
    /* The availability endpoint answers with room types, not prices, so the
     * cheapest room of each type is derived from the room list. */
    var priceByType = {};
    var amenities = {};
    rooms.forEach(function (room) {
      var current = priceByType[room.room_type];
      var price = Number(room.price_per_night);
      if (current === undefined || price < current) priceByType[room.room_type] = price;
      (room.amenities_detail || []).forEach(function (a) {
        amenities[a.name] = true;
      });
    });

    var rating = hotel.average_rating
      ? '<span class="rating"><span class="stars">' + stars(hotel.average_rating) + "</span>" +
        Number(hotel.average_rating).toFixed(1) + '<span class="muted small">· ' +
        plural(hotel.review_count, "review") + "</span></span>"
      : '<span class="muted small">No reviews yet</span>';

    view.innerHTML =
      '<section class="shell" style="padding-top:1.5rem">' +
      '<a class="navlink" href="#/" style="padding-left:0">← All stays</a>' +
      '<div class="cover cover--tall" style="' + coverStyle(hotel.id) + ';margin:.75rem 0 1.25rem">' +
      '<span class="cover__initial">' + initial(hotel.name) + "</span></div>" +
      '<div class="detail">' +
      "<div>" +
      "<h1>" + esc(hotel.name) + "</h1>" +
      '<p class="muted">' + esc(hotel.location) + "</p>" +
      '<div style="margin:.5rem 0 1.25rem">' + rating + "</div>" +
      "<p>" + esc(hotel.description || "No description provided.") + "</p>" +
      (Object.keys(amenities).length
        ? '<h2 style="margin-top:2rem;font-size:1.1rem">What this place offers</h2>' +
          '<ul class="amenities" style="margin-top:.75rem">' +
          Object.keys(amenities)
            .map(function (name) {
              return '<li class="pill">' + esc(name) + "</li>";
            })
            .join("") +
          "</ul>"
        : "") +
      '<h2 style="margin-top:2rem;font-size:1.1rem">Reviews</h2>' +
      '<div class="card card--pad" style="margin-top:.75rem" id="reviews">' +
      renderReviews(reviews) +
      "</div>" +
      (Api.isSignedIn() ? reviewForm(hotel.id) : "") +
      "</div>" +
      '<aside class="booking-panel">' +
      '<div class="card card--pad">' +
      '<h2 style="font-size:1.05rem">Check availability</h2>' +
      '<form id="availform" class="stack" style="margin-top:.9rem">' +
      '<div class="row" style="gap:.6rem">' +
      '<label class="field" style="flex:1"><span>Check in</span>' +
      '<input type="date" name="check_in" value="' + esc(search.check_in) + '" min="' + isoDate(0) + '" required></label>' +
      '<label class="field" style="flex:1"><span>Check out</span>' +
      '<input type="date" name="check_out" value="' + esc(search.check_out) + '" min="' + isoDate(1) + '" required></label>' +
      "</div>" +
      '<div class="row" style="gap:.6rem">' +
      '<label class="field" style="flex:1"><span>Adults</span>' +
      '<input type="number" name="adults" min="1" max="8" value="' + esc(search.adults) + '" required></label>' +
      '<label class="field" style="flex:1"><span>Children</span>' +
      '<input type="number" name="children" min="0" max="8" value="0" required></label>' +
      "</div>" +
      '<button class="btn btn--primary btn--block" type="submit">Search rooms</button>' +
      "</form>" +
      '<div id="availability" style="margin-top:1rem"></div>' +
      "</div></aside></div></section>";

    var availForm = document.getElementById("availform");
    availForm.addEventListener("submit", function (event) {
      event.preventDefault();
      loadAvailability(hotel, priceByType);
    });
    loadAvailability(hotel, priceByType);

    var addReview = document.getElementById("reviewform");
    if (addReview) {
      addReview.addEventListener("submit", function (event) {
        event.preventDefault();
        var values = form("reviewform");
        Api.createReview({
          hotel: hotel.id,
          rating: Number(values.rating),
          comment: values.comment
        })
          .then(function () {
            toast("Thanks for the review.");
            renderHotel(hotel.id);
          })
          .catch(function (err) {
            showErrors(addReview, err);
          });
      });
    }
  }

  function renderReviews(reviews) {
    if (!reviews.length) return '<p class="muted small">No reviews yet — be the first.</p>';
    return reviews
      .map(function (review) {
        return (
          '<article class="review"><div class="review__who">' +
          '<span class="avatar">' + initial(review.username) + "</span>" +
          "<strong>" + esc(review.username) + "</strong>" +
          '<span class="stars small">' + stars(review.rating) + "</span></div>" +
          "<p style='margin:0'>" + esc(review.comment) + "</p></article>"
        );
      })
      .join("");
  }

  function reviewForm(hotelId) {
    return (
      '<form class="card card--pad stack" id="reviewform" style="margin-top:1rem" data-hotel="' +
      hotelId +
      '">' +
      '<h3 style="font-size:1rem">Write a review</h3>' +
      '<label class="field"><span>Rating</span><select name="rating">' +
      [5, 4, 3, 2, 1]
        .map(function (n) {
          return '<option value="' + n + '">' + stars(n) + "</option>";
        })
        .join("") +
      "</select></label>" +
      '<label class="field"><span>Comment</span>' +
      '<textarea name="comment" placeholder="How was your stay?"></textarea></label>' +
      '<button class="btn btn--ghost" type="submit">Post review</button>' +
      "</form>"
    );
  }

  function loadAvailability(hotel, priceByType) {
    var box = document.getElementById("availability");
    var values = form("availform");
    var nights = nightsBetween(values.check_in, values.check_out);

    if (nights < 1) {
      box.innerHTML = '<p class="notice notice--bad">Check-out must be after check-in.</p>';
      return;
    }

    box.innerHTML = '<p class="muted small">Searching…</p>';
    Api.availability({
      hotel: hotel.id,
      check_in: values.check_in,
      check_out: values.check_out,
      adults: values.adults,
      children: values.children
    })
      .then(function (types) {
        if (!types.length) {
          box.innerHTML =
            '<p class="notice notice--info">Nothing free for those dates. Try shifting them, ' +
            "or reducing the party size.</p>";
          return;
        }
        box.innerHTML =
          '<p class="muted small">' + plural(nights, "night") + "</p>" +
          types
            .map(function (type) {
              var price = priceByType[type.id];
              var total = price === undefined ? null : price * nights;
              return (
                '<div class="roomtype"><div><strong>' + esc(type.name) + "</strong>" +
                (total === null
                  ? ""
                  : '<div class="price">' + money(total) +
                    " <span>total · " + money(price) + "/night</span></div>") +
                "</div>" +
                '<button class="btn btn--primary" data-book="' + type.id + '">Book</button></div>'
              );
            })
            .join("");

        box.querySelectorAll("[data-book]").forEach(function (button) {
          button.addEventListener("click", function () {
            book(hotel.id, button.getAttribute("data-book"), values, button);
          });
        });
      })
      .catch(function (err) {
        box.innerHTML = '<p class="notice notice--bad">' + esc(err.message) + "</p>";
      });
  }

  function book(hotelId, roomTypeId, values, button) {
    if (!Api.isSignedIn()) {
      toast("Sign in to book.");
      go("#/login");
      return;
    }
    button.disabled = true;
    button.textContent = "Booking…";
    Api.createBooking({
      hotel: hotelId,
      room_type: Number(roomTypeId),
      check_in: values.check_in,
      check_out: values.check_out,
      adults: Number(values.adults),
      children: Number(values.children)
    })
      .then(function () {
        toast("Booked. Complete the payment to confirm it.");
        go("#/bookings");
      })
      .catch(function (err) {
        button.disabled = false;
        button.textContent = "Book";
        toast(err.message, "bad");
      });
  }

  /* ----------------------------------------------------------------- bookings */

  var STATUS_PILL = { confirmed: "pill--ok", pending: "pill--warn", cancelled: "pill--bad" };

  function renderBookings() {
    view.innerHTML =
      '<section class="section shell">' +
      '<div class="section__head"><h2>My bookings</h2></div>' +
      '<div id="list">' + skeletons(2) + "</div></section>";

    var list = document.getElementById("list");
    Api.bookings()
      .then(function (page) {
        if (!page.results.length) {
          list.innerHTML = empty("🧳", "No bookings yet", "Find a stay and reserve a room.");
          return;
        }
        list.innerHTML = '<div class="stack">' + page.results.map(bookingCard).join("") + "</div>";
        wireBookingActions();
      })
      .catch(function (err) {
        list.innerHTML = '<p class="notice notice--bad">' + esc(err.message) + "</p>";
      });
  }

  function bookingCard(booking) {
    var payment = booking.payment || {};
    var rooms = (booking.rooms || [])
      .map(function (room) {
        return "Room " + esc(room.room_number) + " · " + esc(room.room_type_name);
      })
      .join(", ");

    var actions = [];
    if (payment.status === "pending" && payment.payment_url) {
      actions.push(
        '<a class="btn btn--primary" href="' + esc(payment.payment_url) + '">Pay ' +
          money(payment.amount) + "</a>"
      );
      /* The offline provider never calls the webhook back, so the demo offers
       * to deliver the event itself. With a real acquirer configured this call
       * is rejected: the endpoint verifies the provider's signature. */
      if (payment.provider === "fake") {
        actions.push(
          '<button class="btn btn--ghost" data-settle="' + esc(payment.payment_url) +
            '" title="Delivers the payment webhook the offline provider cannot send">' +
            "Simulate payment</button>"
        );
      }
    }
    if (booking.status !== "cancelled") {
      actions.push('<button class="btn btn--quiet" data-cancel="' + booking.id + '">Cancel</button>');
    }

    return (
      '<article class="card booking">' +
      "<div><div class='row' style='gap:.5rem'>" +
      "<strong>" + esc(booking.hotel_name) + "</strong>" +
      '<span class="pill ' + (STATUS_PILL[booking.status] || "") + '">' + esc(booking.status) + "</span>" +
      "</div>" +
      '<div class="dates">' + prettyDate(booking.check_in) + " → " + prettyDate(booking.check_out) +
      " · " + plural(booking.nights, "night") +
      " · " + plural(booking.adults, "adult") +
      (booking.children ? ", " + plural(booking.children, "child", "children") : "") +
      "</div>" +
      '<div class="muted small">' + rooms + "</div></div>" +
      '<div class="row">' + actions.join("") + "</div></article>"
    );
  }

  function wireBookingActions() {
    document.querySelectorAll("[data-cancel]").forEach(function (button) {
      button.addEventListener("click", function () {
        button.disabled = true;
        Api.cancelBooking(button.getAttribute("data-cancel"))
          .then(function () {
            toast("Booking cancelled — the room is free again.");
            renderBookings();
          })
          .catch(function (err) {
            button.disabled = false;
            toast(err.message, "bad");
          });
      });
    });

    document.querySelectorAll("[data-settle]").forEach(function (button) {
      button.addEventListener("click", function () {
        /* The fake provider encodes the invoice id in the payment URL. */
        var invoice = new URL(
          button.getAttribute("data-settle"),
          window.location.origin
        ).searchParams.get("invoice");
        if (!invoice) return toast("No invoice id on that payment link.", "bad");

        button.disabled = true;
        Api.settleFakePayment(invoice)
          .then(function () {
            toast("Payment confirmed.");
            renderBookings();
          })
          .catch(function (err) {
            button.disabled = false;
            toast(err.message, "bad");
          });
      });
    });
  }

  /* --------------------------------------------------------------------- auth */

  function renderAuth(mode) {
    var isRegister = mode === "register";
    view.innerHTML =
      '<section class="authwrap shell">' +
      '<div class="tabs">' +
      '<a href="#/login"' + (isRegister ? "" : ' aria-current="page"') + ">Sign in</a>" +
      '<a href="#/register"' + (isRegister ? ' aria-current="page"' : "") + ">Create account</a>" +
      "</div>" +
      '<form class="card card--pad stack" id="authform">' +
      '<label class="field"><span>Username</span><input name="username" autocomplete="username" required></label>' +
      (isRegister
        ? '<label class="field"><span>Email</span><input type="email" name="email" autocomplete="email" required></label>'
        : "") +
      '<label class="field"><span>Password</span><input type="password" name="password" autocomplete="' +
      (isRegister ? "new-password" : "current-password") +
      '" required></label>' +
      '<button class="btn btn--primary btn--block" type="submit">' +
      (isRegister ? "Create account" : "Sign in") +
      "</button>" +
      (isRegister
        ? '<p class="muted small" style="margin:0">Passwords go through Django\'s validators, so ' +
          "short or common ones are rejected.</p>"
        : '<p class="muted small" style="margin:0">Demo accounts: <code>guest1</code> / ' +
          "<code>DemoPassw0rd!42</code></p>") +
      "</form></section>";

    var element = document.getElementById("authform");
    element.addEventListener("submit", function (event) {
      event.preventDefault();
      var values = form("authform");
      var button = element.querySelector("button");
      button.disabled = true;

      var action = isRegister
        ? Api.register(values).then(function () {
            return Api.login(values.username, values.password);
          })
        : Api.login(values.username, values.password);

      action
        .then(loadUser)
        .then(function () {
          toast(isRegister ? "Welcome aboard." : "Signed in.");
          go("#/");
        })
        .catch(function (err) {
          button.disabled = false;
          showErrors(element, err);
        });
    });
  }

  function loadUser() {
    return Api.me()
      .then(function (user) {
        state.user = user;
        renderNav();
        return user;
      })
      .catch(function () {
        state.user = null;
        renderNav();
      });
  }

  /* ------------------------------------------------------------------- router */

  function route() {
    var hash = window.location.hash || "#/";
    var hotelMatch = hash.match(/^#\/hotels\/(\d+)$/);

    window.scrollTo(0, 0);
    if (hotelMatch) renderHotel(hotelMatch[1]);
    else if (hash === "#/login") renderAuth("login");
    else if (hash === "#/register") renderAuth("register");
    else if (hash === "#/bookings") {
      if (!Api.isSignedIn()) {
        toast("Sign in to see your bookings.");
        return go("#/login");
      }
      renderBookings();
    } else renderHome();

    renderNav();
  }

  window.addEventListener("hashchange", route);

  Api.restore()
    .then(function (signedIn) {
      return signedIn ? loadUser() : null;
    })
    .then(route);
})(window, document);
