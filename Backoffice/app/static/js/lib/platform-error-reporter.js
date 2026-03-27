/**
 * Reports platform-level errors (WAF 403, 502, 503) to /api/v1/platform-error.
 *
 * When a WAF or reverse-proxy intercepts an AJAX request and returns an
 * HTML error page, the beacon script embedded in that page never executes.
 * This module bridges that gap: window.fetch is wrapped so any non-OK
 * response that looks like a proxy/WAF page triggers reportPlatformError().
 *
 * Deduplication: each (status, page path, failed-request path) is reported at
 * most once per page session (sessionStorage).
 */
(function () {
  'use strict';

  var REPORTABLE_CODES = [403, 502, 503];
  var ENDPOINT = '/api/v1/platform-error';
  var WRAP_FLAG = '__ngodbPlatformErrorFetchWrapped';

  var nativeFetch =
    typeof window !== 'undefined' && typeof window.fetch === 'function'
      ? window.fetch.bind(window)
      : null;

  function shouldReport(statusCode) {
    return REPORTABLE_CODES.indexOf(statusCode) !== -1;
  }

  function pathnameForDedupe(urlStr) {
    if (!urlStr) return '';
    try {
      return new URL(urlStr, window.location.origin).pathname || '';
    } catch (_) {
      return String(urlStr).slice(0, 200);
    }
  }

  function dedupeKey(statusCode, failedRequestUrl) {
    var pagePath = (window.location && window.location.pathname) || '';
    var apiPath = pathnameForDedupe(failedRequestUrl);
    return 'platform_err_' + statusCode + '_' + pagePath + '_' + apiPath;
  }

  function alreadyReported(statusCode, failedRequestUrl) {
    try {
      return !!sessionStorage.getItem(dedupeKey(statusCode, failedRequestUrl));
    } catch (_) {
      return false;
    }
  }

  function markReported(statusCode, failedRequestUrl) {
    try {
      sessionStorage.setItem(dedupeKey(statusCode, failedRequestUrl), '1');
    } catch (_) {}
  }

  /**
   * Detect whether a fetch Response looks like a WAF / reverse-proxy error
   * rather than a Flask-generated JSON response.
   *
   * @param {Response} response - The fetch Response object
   * @returns {boolean}
   */
  function looksLikeWafResponse(response) {
    if (!response || typeof response.status !== 'number') return false;
    if (!shouldReport(response.status)) return false;

    var ct = '';
    try {
      ct = (response.headers.get('Content-Type') || '').toLowerCase();
    } catch (_) {}
    return !ct.includes('application/json');
  }

  function requestUrlFromFetchInput(input) {
    try {
      if (typeof input === 'string') return input;
      if (input && typeof input.url === 'string') return input.url;
    } catch (_) {}
    return window.location.href;
  }

  function isPlatformErrorRequestUrl(urlStr) {
    try {
      var p = pathnameForDedupe(urlStr);
      return p.indexOf('/api/v1/platform-error') !== -1;
    } catch (_) {
      return false;
    }
  }

  /**
   * Report a platform-level error to the backend.
   *
   * Safe to call speculatively — it no-ops when the status code is not
   * reportable, the response looks like a normal Flask JSON error, or the
   * same error was already reported this session.
   *
   * @param {Response} response - The original fetch Response
   * @param {object}   [opts]
   * @param {string}   [opts.url]      - URL of the failed request (default: current page)
   * @param {string}   [opts.referrer] - Override referrer
   */
  function reportPlatformError(response, opts) {
    if (!response || typeof response.status !== 'number') return;
    var code = response.status;
    if (!shouldReport(code)) return;
    if (!looksLikeWafResponse(response)) return;

    var o = opts || {};
    var failedUrl = o.url || window.location.href;
    if (alreadyReported(code, failedUrl)) return;

    markReported(code, failedUrl);

    var payload = {
      error_code: code,
      url: failedUrl,
      referrer: o.referrer || document.referrer || null,
      user_agent: navigator.userAgent || null,
      timestamp: new Date().toISOString()
    };

    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(
          ENDPOINT,
          new Blob([JSON.stringify(payload)], { type: 'application/json' })
        );
      } else if (nativeFetch) {
        nativeFetch(ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          keepalive: true
        }).catch(function () {});
      }
    } catch (_) {}
  }

  function installFetchWrapper() {
    if (!nativeFetch || window[WRAP_FLAG]) return;
    window[WRAP_FLAG] = true;
    window.fetch = function (input, init) {
      var reqUrl = requestUrlFromFetchInput(input);
      return nativeFetch(input, init).then(function (response) {
        if (
          response &&
          !response.ok &&
          !isPlatformErrorRequestUrl(reqUrl) &&
          typeof reportPlatformError === 'function'
        ) {
          reportPlatformError(response, { url: reqUrl });
        }
        return response;
      });
    };
  }

  if (typeof window !== 'undefined') {
    window.reportPlatformError = reportPlatformError;
    window.looksLikeWafResponse = looksLikeWafResponse;
    installFetchWrapper();
  }
})();
