/**
 * Shared AutoTranslateService for /admin/api/auto-translate.
 * Use this instead of inline fetch calls to centralize CSRF, headers, and error handling.
 *
 * Depends on: csrf.js (csrfFetch), TranslationModalUtils.handleAutoTranslateResponse (optional)
 *
 * Usage:
 *   const data = await AutoTranslateService.translate({
 *     type: 'form_item',
 *     text: 'Label text',
 *     target_languages: ['fr', 'es'],
 *     permission_context: 'indicator_bank',
 *     permission_code: 'admin.indicator_bank.edit'
 *   });
 */
(function() {
    'use strict';

    const AUTO_TRANSLATE_URL = '/admin/api/auto-translate';
    const fetchFn = (window.getFetch && window.getFetch()) || (typeof fetch !== 'undefined' ? fetch : null);

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function handleResponse(response) {
        if (!response) {
            return Promise.reject(new Error('No response from translation service'));
        }
        const parseJsonSafe = () =>
            response.clone().json().catch(() => ({}));

        if (!response.ok) {
            return parseJsonSafe().then(data => {
                const message = (data && (data.error || data.message)) ||
                    `HTTP ${response.status}: ${response.statusText || 'Unknown error'}`;
                throw (window.httpErrorSync && window.httpErrorSync(response, message)) || new Error(message);
            });
        }
        return response.json().then(data => {
            if (!data || !data.success) {
                throw new Error((data && (data.error || data.message)) || 'Translation failed');
            }
            return data;
        });
    }

    /**
     * Call the auto-translate API.
     * @param {Object} params
     * @param {string} params.type - API type (e.g. 'template_name', 'form_item', 'section_name', 'page_name', 'question_option')
     * @param {string} params.text - Text to translate
     * @param {string[]} params.target_languages - Target language codes
     * @param {string} [params.permission_context] - Permission context
     * @param {string} [params.permission_code] - Permission code
     * @param {string} [params.translation_service] - e.g. 'ifrc'
     * @param {string} [params.definition] - Optional definition
     * @returns {Promise<{success: boolean, translations: Object}>}
     */
    async function translate(params) {
        const body = {
            type: params.type || 'template_name',
            text: params.text || '',
            target_languages: params.target_languages || []
        };
        if (params.permission_context != null) body.permission_context = params.permission_context;
        if (params.permission_code != null) body.permission_code = params.permission_code;
        if (params.translation_service != null) body.translation_service = params.translation_service;
        if (params.definition != null) body.definition = params.definition;

        const response = await fetchFn(AUTO_TRANSLATE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(body)
        });

        if (typeof window !== 'undefined' && window.TranslationModalUtils && window.TranslationModalUtils.handleAutoTranslateResponse) {
            return window.TranslationModalUtils.handleAutoTranslateResponse(response);
        }
        return handleResponse(response);
    }

    if (typeof window !== 'undefined') {
        window.AutoTranslateService = { translate };
    }
})();
