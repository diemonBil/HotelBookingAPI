/* Client for the Hotel Booking API.
 *
 * Loaded as a classic script rather than an ES module on purpose: WhiteNoise's
 * ManifestStaticFilesStorage hashes static filenames in production but does not
 * rewrite import specifiers inside JavaScript, so a relative `import` would
 * resolve to a name that no longer exists. Two plain scripts sharing one global
 * avoid the problem entirely.
 */
(function (window) {
  "use strict";

  var BASE = "/api/v1";
  var REFRESH_KEY = "hotelbooking.refresh";

  /* The access token lives in memory only. A reload re-derives it from the
   * refresh token, which keeps the short-lived credential out of any storage
   * an injected script could read. A production deployment would go further and
   * hold the refresh token in an httpOnly cookie. */
  var accessToken = null;

  function getRefreshToken() {
    try {
      return window.localStorage.getItem(REFRESH_KEY);
    } catch (err) {
      return null; // Private browsing modes can throw on access.
    }
  }

  function setRefreshToken(token) {
    try {
      if (token) {
        window.localStorage.setItem(REFRESH_KEY, token);
      } else {
        window.localStorage.removeItem(REFRESH_KEY);
      }
    } catch (err) {
      /* Storage unavailable: the session simply will not survive a reload. */
    }
  }

  function ApiError(status, payload) {
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
    this.message = ApiError.describe(status, payload);
  }
  ApiError.prototype = Object.create(Error.prototype);

  /* Turn a DRF error body into one readable sentence. DRF answers with
   * {"detail": "..."}, {"field": ["..."]} or a bare list, depending on where
   * validation failed. */
  ApiError.describe = function (status, payload) {
    if (!payload) {
      return status === 0 ? "Network error — is the API running?" : "Request failed (" + status + ")";
    }
    if (typeof payload === "string") return payload;
    if (payload.detail) return payload.detail;

    var parts = [];
    if (Array.isArray(payload)) {
      parts = payload.map(String);
    } else {
      Object.keys(payload).forEach(function (key) {
        var value = payload[key];
        var text = Array.isArray(value) ? value.join(" ") : String(value);
        parts.push(key === "non_field_errors" ? text : key.replace(/_/g, " ") + ": " + text);
      });
    }
    return parts.join(" ") || "Request failed (" + status + ")";
  };

  ApiError.prototype.fieldErrors = function () {
    return this.payload && typeof this.payload === "object" && !Array.isArray(this.payload)
      ? this.payload
      : {};
  };

  function buildUrl(path, params) {
    var url = BASE + path;
    if (!params) return url;
    var query = new URLSearchParams();
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (value !== undefined && value !== null && value !== "") query.set(key, value);
    });
    var qs = query.toString();
    return qs ? url + "?" + qs : url;
  }

  function send(method, path, options) {
    options = options || {};
    var headers = { Accept: "application/json" };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (accessToken && options.auth !== false) {
      headers.Authorization = "Bearer " + accessToken;
    }

    return window
      .fetch(buildUrl(path, options.params), {
        method: method,
        headers: headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body)
      })
      .then(function (response) {
        if (response.status === 204) return null;
        return response
          .json()
          .catch(function () {
            return null;
          })
          .then(function (data) {
            if (!response.ok) throw new ApiError(response.status, data);
            return data;
          });
      })
      .catch(function (err) {
        if (err instanceof ApiError) throw err;
        throw new ApiError(0, null); // fetch itself failed: offline, DNS, CORS
      });
  }

  /* Retry once through a token refresh when the access token has expired.
   * Anything else — a genuine 403, a validation error — is passed straight on. */
  function request(method, path, options) {
    return send(method, path, options).catch(function (err) {
      var canRetry = err.status === 401 && options && options.auth !== false && getRefreshToken();
      if (!canRetry) throw err;
      return refresh().then(function () {
        return send(method, path, options);
      });
    });
  }

  function refresh() {
    var token = getRefreshToken();
    if (!token) return Promise.reject(new ApiError(401, { detail: "Not signed in." }));

    return send("POST", "/user/token/refresh/", { body: { refresh: token }, auth: false })
      .then(function (data) {
        accessToken = data.access;
        // ROTATE_REFRESH_TOKENS is on, so the server hands back a fresh one.
        if (data.refresh) setRefreshToken(data.refresh);
        return data;
      })
      .catch(function (err) {
        setRefreshToken(null);
        accessToken = null;
        throw err;
      });
  }

  var Api = {
    ApiError: ApiError,

    isSignedIn: function () {
      return Boolean(accessToken || getRefreshToken());
    },

    /* Called once at start-up: turns a stored refresh token back into a
     * usable session, or reports that there is none. */
    restore: function () {
      if (accessToken) return Promise.resolve(true);
      if (!getRefreshToken()) return Promise.resolve(false);
      return refresh()
        .then(function () {
          return true;
        })
        .catch(function () {
          return false;
        });
    },

    login: function (username, password) {
      return send("POST", "/user/login/", {
        body: { username: username, password: password },
        auth: false
      }).then(function (data) {
        accessToken = data.access;
        setRefreshToken(data.refresh);
        return data;
      });
    },

    register: function (payload) {
      return send("POST", "/user/register/", { body: payload, auth: false });
    },

    logout: function () {
      accessToken = null;
      setRefreshToken(null);
    },

    me: function () {
      return request("GET", "/user/me/", {});
    },

    hotels: function (params) {
      return request("GET", "/hotels/", { params: params, auth: false });
    },

    hotel: function (id) {
      return request("GET", "/hotels/" + id + "/", { auth: false });
    },

    rooms: function (params) {
      return request("GET", "/rooms/", { params: params, auth: false });
    },

    availability: function (params) {
      return request("GET", "/availability/room-types/", { params: params, auth: false });
    },

    reviews: function (params) {
      return request("GET", "/reviews/", { params: params, auth: false });
    },

    createReview: function (payload) {
      return request("POST", "/reviews/", { body: payload });
    },

    bookings: function () {
      return request("GET", "/bookings/", {});
    },

    createBooking: function (payload) {
      return request("POST", "/bookings/", { body: payload });
    },

    cancelBooking: function (id) {
      return request("POST", "/bookings/" + id + "/cancel/", { body: {} });
    },

    /* Demo only. The fake provider has no way to call us back, so the client
     * posts the event itself. Against a real acquirer this is rejected: the
     * endpoint verifies the provider's signature over the request body. */
    settleFakePayment: function (invoiceId) {
      return request("POST", "/payments/webhook/", {
        body: { invoiceId: invoiceId, status: "success" },
        auth: false
      });
    }
  };

  window.Api = Api;
})(window);
