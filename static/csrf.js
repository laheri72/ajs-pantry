// Shared CSRF wiring: attaches the token to same-origin fetch() calls and
// classic HTML form POSTs so Flask-WTF's CSRFProtect can validate them.
(function () {
    function getToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : null;
    }

    var token = getToken();
    if (!token) {
        return;
    }

    var unsafeMethods = ['POST', 'PUT', 'PATCH', 'DELETE'];

    var originalFetch = window.fetch;
    window.fetch = function (input, init) {
        init = init || {};
        var method = (init.method || (input && input.method) || 'GET').toUpperCase();

        var url = typeof input === 'string' ? input : (input && input.url) || '';
        var isSameOrigin = !/^([a-z]+:)?\/\//i.test(url) || url.indexOf(window.location.origin) === 0;

        if (unsafeMethods.indexOf(method) !== -1 && isSameOrigin) {
            var headers = new Headers(init.headers || (input && input.headers) || {});
            if (!headers.has('X-CSRFToken')) {
                headers.set('X-CSRFToken', token);
            }
            init = Object.assign({}, init, { headers: headers });
        }

        return originalFetch.call(this, input, init);
    };

    function injectIntoForms() {
        var forms = document.querySelectorAll('form[method="post"], form[method="POST"]');
        forms.forEach(function (form) {
            if (form.querySelector('input[name="csrf_token"]')) {
                return;
            }
            var input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = token;
            form.appendChild(input);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectIntoForms);
    } else {
        injectIntoForms();
    }
})();
