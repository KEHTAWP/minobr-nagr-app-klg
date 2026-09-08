/* Логика приложения: выбор награды → анкета → формирование пакета документов.
   Введённые сведения хранятся только в памяти и стираются после сохранения PDF. */

(function () {
    'use strict';

    var state = {
        levels: [],
        award: null,
        status: null,
        schema: null,
        step: 0,
        data: {},
        history: [],
        result: null,
        developer: false
    };

    var el = function (id) { return document.getElementById(id); };

    /* ------------------------------------------------------------ связь */

    /* Страница всегда открыта с локального сервера — и в собственном окне
       программы, и во вкладке браузера. Раньше окно общалось с Python
       напрямую через мост pywebview, и это приводило к зависаниям: мост
       обслуживал вызовы тем же потоком, который рисует окно. Теперь путь
       один и тот же, а разница между режимами только в том, доступны ли
       системные диалоги (сохранение файла, открытие папки). */

    function nativeMode() {
        return window.PORTAL_NATIVE === true;
    }

    function call(method, arg) {
        return fetch('/api/' + method, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Portal-Key': window.PORTAL_KEY || ''
            },
            body: JSON.stringify(arg === undefined ? [] : [arg])
        }).then(function (r) {
            if (!r.ok) {
                throw new Error('Программа ответила с ошибкой ' + r.status + '.');
            }
            return r.json();
        });
    }

    /* ---------------------------------------------------------- экраны */

    var SCREENS = ['screen-home', 'screen-award', 'screen-form', 'screen-done'];

    function show(id) {
        SCREENS.forEach(function (s) {
            el(s).classList.toggle('hidden', s !== id);
        });
        el('search-wrapper').classList.toggle('hidden', id !== 'screen-home');
        window.scrollTo(0, 0);
    }

    function overlay(on, text) {
        el('overlay').classList.toggle('hidden', !on);
        if (text) { el('overlay-text').textContent = text; }
    }

    /* ------------------------------------------------- экран: главная */

    function renderHome() {
        var box = el('levels-container');
        box.innerHTML = '';

        state.levels.forEach(function (lvl) {
            var item = document.createElement('div');
            item.className = 'level-item';

            var head = document.createElement('div');
            head.className = 'level-header';
            head.innerHTML = '<span>' + lvl.title + '</span><span class="arrow">➤</span>';
            head.addEventListener('click', function () {
                item.classList.toggle('expanded');
            });

            var grid = document.createElement('div');
            grid.className = 'awards-container';

            lvl.awards.forEach(function (award) {
                var st = award.status || { open: true };

                var tile = document.createElement('div');
                tile.className = 'award-tile' + (st.open ? '' : ' locked');
                tile.dataset.name = (award.titlePlain || '').toLowerCase();

                var h = document.createElement('h4');
                h.innerHTML = award.tile || award.title;

                var btn = document.createElement('button');
                btn.className = 'btn-choose';
                /* Закрытую награду выбрать нельзя, но прочитать о ней можно:
                   описание и требования нужны и до начала приёма. */
                btn.textContent = st.open ? 'Выбрать' : 'Подробнее';
                btn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    openAward(award.id);
                });

                tile.appendChild(h);

                /* Срок подачи истекает совсем скоро — заметная пометка */
                if (st.warning && st.message) {
                    var alert = document.createElement('div');
                    alert.className = 'award-alert';
                    alert.textContent = '!';
                    alert.setAttribute('data-tip', st.message);
                    tile.appendChild(alert);
                }

                if (award.period) {
                    var p = document.createElement('div');
                    p.className = 'award-period';
                    p.textContent = award.period;
                    tile.appendChild(p);
                }
                if (!st.open && st.message) {
                    var closed = document.createElement('div');
                    closed.className = 'award-closed';
                    closed.textContent = st.message;
                    tile.appendChild(closed);
                }
                tile.appendChild(btn);
                grid.appendChild(tile);
            });

            var period = document.createElement('div');
            period.className = 'review-period';
            period.textContent = lvl.review;

            item.appendChild(head);
            item.appendChild(grid);
            item.appendChild(period);
            box.appendChild(item);
        });
    }

    function performSearch() {
        var q = el('search-input').value.trim().toLowerCase();
        var tiles = document.querySelectorAll('.award-tile');
        tiles.forEach(function (t) { t.classList.remove('highlight'); });
        if (!q) { return; }

        var words = q.split(/\s+/).filter(Boolean);
        var found = false;

        document.querySelectorAll('.level-item').forEach(function (lvl) {
            var hit = false;
            lvl.querySelectorAll('.award-tile').forEach(function (tile) {
                if (words.some(function (w) { return tile.dataset.name.indexOf(w) >= 0; })) {
                    tile.classList.add('highlight');
                    hit = true;
                    found = true;
                }
            });
            if (hit) { lvl.classList.add('expanded'); }
        });

        if (!found) {
            alert('Наград, содержащих указанные слова, не найдено.');
        }
    }

    /* ------------------------------------- экран: информация о награде */

    function openAward(awardId) {
        overlay(true, 'Загружаем сведения о награде…');
        call('get_award', awardId).then(function (res) {
            overlay(false);
            if (!res.ok) { return fail(res.error); }
            state.award = res.award;
            state.status = res.status || { open: true };
            el('award-title').innerHTML = res.award.title;

            var box = el('award-blocks');
            box.innerHTML = '';

            /* Если приём закрыт, об этом говорится сразу и заметно, а кнопка
               перехода к анкете убирается — заполнять её сейчас незачем. */
            if (!state.status.open && state.status.message) {
                var notice = document.createElement('div');
                notice.className = 'closed-notice';
                notice.innerHTML = '<strong>Приём документов закрыт.</strong><br>' +
                    state.status.message;
                box.appendChild(notice);
            } else if (state.status.warning && state.status.message) {
                var soon = document.createElement('div');
                soon.className = 'closed-notice';
                soon.innerHTML = '<strong>Срок подачи заканчивается.</strong><br>' +
                    state.status.message;
                box.appendChild(soon);
            }

            res.award.blocks.forEach(function (b) {
                var div = document.createElement('div');
                div.className = 'info-block';
                div.innerHTML = '<h3>' + b.h + '</h3><p>' + b.body + '</p>';
                box.appendChild(div);
            });
            document.querySelectorAll('[data-action="start-form"]')
                .forEach(function (b) {
                    b.classList.toggle('hidden', !state.status.open);
                });
            show('screen-award');
        }).catch(function (e) { overlay(false); fail(e.message); });
    }

    /* ---------------------------------------------------- экран: анкета */

    function startForm() {
        overlay(true, 'Готовим анкету…');
        call('get_schema', state.award.id).then(function (res) {
            overlay(false);
            if (!res.ok) { return fail(res.error); }
            state.schema = res.schema;
            state.step = 0;
            state.data = { award_id: state.award.id };
            state.history = [{ from: '', to: '', position: '', address: '' }];
            el('form-award-title').innerHTML = state.schema.award_title_html;
            renderStep();
            show('screen-form');
        }).catch(function (e) { overlay(false); fail(e.message); });
    }

    function totalSteps() {
        return state.schema.steps.length + 1;   // + итоговая проверка
    }

    function renderSteps() {
        var bar = el('steps-bar');
        bar.innerHTML = '';
        var titles = state.schema.steps.map(function (s) { return s.title; });
        titles.push('Проверка');
        titles.forEach(function (t, i) {
            var chip = document.createElement('span');
            chip.className = 'step-chip' +
                (i === state.step ? ' active' : (i < state.step ? ' done' : ''));
            chip.textContent = (i + 1) + '. ' + t;
            bar.appendChild(chip);
        });
    }

    function renderStep() {
        renderSteps();
        var body = el('step-body');
        body.innerHTML = '';

        if (state.step >= state.schema.steps.length) {
            body.appendChild(buildSummary());
            el('btn-next').textContent = 'Сформировать PDF';
        } else {
            body.appendChild(buildStep(state.schema.steps[state.step]));
            el('btn-next').textContent = 'Далее →';
        }
        el('btn-prev').textContent = state.step === 0 ? '← К награде' : '← Назад';
    }

    function buildStep(step) {
        var card = document.createElement('div');
        card.className = 'form-card';

        var h = document.createElement('h3');
        h.textContent = step.title;
        card.appendChild(h);

        if (step.hint) {
            var hint = document.createElement('div');
            hint.className = 'hint';
            hint.textContent = step.hint;
            card.appendChild(hint);
        }

        step.fields.forEach(function (f) { card.appendChild(buildField(f)); });

        if (step.table) { card.appendChild(buildTable(step.table)); }
        return card;
    }

    function buildField(f) {
        var wrap = document.createElement('div');
        wrap.className = 'field';

        var label = document.createElement('label');
        label.innerHTML = f.label + (f.required ? '<span class="req">*</span>' : '');
        if (f.hint) {
            label.innerHTML += '<span class="sub">' + f.hint + '</span>';
        }
        wrap.appendChild(label);

        var input;
        if (f.kind === 'date') {
            /* Дата выбирается календариком. В анкете и в документах она
               живёт в привычном виде «дд.мм.гггг», а поле такого типа
               работает с «гггг-мм-дд» — поэтому значение переводится
               туда и обратно. */
            input = document.createElement('input');
            input.type = 'date';
            input.className = 'date-input';
        } else if (f.kind === 'textarea') {
            input = document.createElement('textarea');
        } else if (f.kind === 'select') {
            input = document.createElement('select');
            var empty = document.createElement('option');
            empty.value = '';
            empty.textContent = '— не выбрано —';
            input.appendChild(empty);
            (f.options || []).forEach(function (o) {
                var opt = document.createElement('option');
                opt.value = o;
                opt.textContent = o;
                input.appendChild(opt);
            });
        } else {
            input = document.createElement('input');
            input.type = 'text';
        }
        input.id = 'fld-' + f.key;
        if (f.kind === 'date') {
            input.value = toDateInput(state.data[f.key] || '');
        } else {
            input.value = state.data[f.key] || '';
        }
        if (f.placeholder && f.kind !== 'select' && f.kind !== 'date') {
            input.placeholder = f.placeholder;
        }
        if (f.numeric) {
            input.setAttribute('inputmode', 'numeric');
        }
        function store() {
            if (f.numeric) {
                // в поле стажа допустимы только цифры
                var cleaned = input.value.replace(/[^0-9]/g, '');
                if (cleaned !== input.value) { input.value = cleaned; }
            }
            state.data[f.key] = f.kind === 'date'
                ? fromDateInput(input.value)
                : input.value;
            input.classList.remove('invalid');
            var err = wrap.querySelector('.field-error');
            if (err) { err.remove(); }
        }
        input.addEventListener('input', store);
        input.addEventListener('change', store);

        if (f.kind === 'date') {
            /* Рядом с календариком — выбранная дата словами и, для даты
               рождения, число полных лет. Если промахнуться мимо нужного
               года, несоответствие видно сразу. */
            var row = document.createElement('div');
            row.className = 'date-row';
            var info = document.createElement('span');
            info.className = 'date-info';

            function refresh() {
                var value = fromDateInput(input.value);
                if (!value) { info.textContent = ''; return; }
                var text = value;
                info.classList.remove('bad');
                if (f.age) {
                    var years = fullYears(value);
                    if (years === null || years < 0 || years > 110) {
                        info.classList.add('bad');
                        text += ' — проверьте год: возраст получается ' +
                            'неправдоподобным';
                    } else {
                        text += ' — возраст ' + years + ' ' +
                            yearsWord(years);
                        if (years < 18) { info.classList.add('bad'); }
                    }
                }
                info.textContent = text;
            }

            input.addEventListener('input', refresh);
            input.addEventListener('change', refresh);
            row.appendChild(input);
            row.appendChild(info);
            wrap.appendChild(row);
            refresh();
        } else {
            wrap.appendChild(input);
        }

        if (f.note) {
            var note = document.createElement('div');
            note.className = 'field-note';
            note.textContent = f.note;
            wrap.appendChild(note);
        }
        return wrap;
    }

    /* --------------------------------------------------------- даты */

    /* Сколько полных лет исполнилось к сегодняшнему дню. */
    function fullYears(value) {
        var m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec((value || '').trim());
        if (!m) { return null; }
        var day = parseInt(m[1], 10), month = parseInt(m[2], 10),
            year = parseInt(m[3], 10);
        var now = new Date();
        var years = now.getFullYear() - year;
        var passed = (now.getMonth() + 1) > month ||
            ((now.getMonth() + 1) === month && now.getDate() >= day);
        if (!passed) { years -= 1; }
        return years;
    }

    function yearsWord(n) {
        var rest = Math.abs(n) % 100;
        if (rest >= 11 && rest <= 14) { return 'лет'; }
        rest %= 10;
        if (rest === 1) { return 'год'; }
        if (rest >= 2 && rest <= 4) { return 'года'; }
        return 'лет';
    }

    /* «дд.мм.гггг» -> «гггг-мм-дд» для календарика и обратно. */
    function toDateInput(value) {
        var m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec((value || '').trim());
        return m ? m[3] + '-' + m[2] + '-' + m[1] : '';
    }

    function fromDateInput(value) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value || '').trim());
        return m ? m[3] + '.' + m[2] + '.' + m[1] : (value || '');
    }

    /* --------------------------------------------------------- проверки */

    /* Проверка одного поля: обязательность и минимальный стаж. */
    function fieldError(f) {
        var value = (state.data[f.key] || '').trim();
        if (f.required && !value) {
            return 'Поле обязательно для заполнения.';
        }
        if (value && f.min !== undefined) {
            var num = parseInt(value.replace(/[^0-9]/g, ''), 10);
            if (isNaN(num)) { return 'Укажите число полных лет.'; }
            if (num < f.min) { return f.minMessage; }
        }
        return chainError(f.key) || null;
    }

    /* Каждый следующий вид стажа входит в предыдущий, поэтому не может быть
       больше него: общий >= в сфере >= в организации >= в должности. */
    function chainError(key) {
        var chain = (state.schema && state.schema.stazh_chain) || [];
        var idx = -1, i;
        for (i = 0; i < chain.length; i++) {
            if (chain[i].key === key) { idx = i; }
        }
        if (idx < 1) { return null; }

        var value = parseInt((state.data[key] || '').replace(/[^0-9]/g, ''), 10);
        if (isNaN(value)) { return null; }

        for (i = 0; i < idx; i++) {
            var above = parseInt(
                (state.data[chain[i].key] || '').replace(/[^0-9]/g, ''), 10);
            if (!isNaN(above) && value > above) {
                return 'Не может быть больше, чем ' + chain[i].label +
                    ' (' + above + '): этот стаж является его частью.';
            }
        }
        return null;
    }

    function buildTable(table) {
        var box = document.createElement('div');

        function redraw() {
            box.innerHTML = '';
            state.history.forEach(function (row, idx) {
                var card = document.createElement('div');
                card.className = 'history-row';

                var num = document.createElement('div');
                num.className = 'rownum';
                num.textContent = 'Запись ' + (idx + 1);
                card.appendChild(num);

                var narrow = document.createElement('div');
                narrow.className = 'field-row';
                var wide = document.createElement('div');

                table.columns.forEach(function (col) {
                    var fw = document.createElement('div');
                    fw.className = 'field';
                    var lb = document.createElement('label');
                    lb.textContent = col.label;
                    var inp = document.createElement('input');
                    inp.type = 'text';
                    inp.value = row[col.key] || '';
                    if (col.placeholder) { inp.placeholder = col.placeholder; }
                    inp.addEventListener('input', function () {
                        row[col.key] = inp.value;
                    });
                    fw.appendChild(lb);
                    fw.appendChild(inp);
                    if (col.note) {
                        var cn = document.createElement('div');
                        cn.className = 'field-note';
                        cn.textContent = col.note;
                        fw.appendChild(cn);
                    }
                    (col.width === 'narrow' ? narrow : wide).appendChild(fw);
                });

                card.appendChild(narrow);
                card.appendChild(wide);

                if (state.history.length > 1) {
                    var del = document.createElement('button');
                    del.className = 'btn-small btn-danger';
                    del.textContent = 'Удалить запись';
                    del.addEventListener('click', function () {
                        state.history.splice(idx, 1);
                        redraw();
                    });
                    card.appendChild(del);
                }
                box.appendChild(card);
            });

            var actions = document.createElement('div');
            actions.className = 'history-actions';
            var add = document.createElement('button');
            add.className = 'btn-small';
            add.textContent = '+ Добавить запись';
            add.addEventListener('click', function () {
                state.history.push({ from: '', to: '', position: '', address: '' });
                redraw();
            });
            actions.appendChild(add);
            box.appendChild(actions);
        }

        redraw();
        return box;
    }

    function buildSummary() {
        var card = document.createElement('div');
        card.className = 'form-card';

        var h = document.createElement('h3');
        h.textContent = 'Проверка перед формированием';
        card.appendChild(h);

        var hint = document.createElement('div');
        hint.className = 'hint';
        hint.textContent = 'Будет создан один PDF-файл. Каждый бланк ' +
            'начинается с новой страницы.';
        card.appendChild(hint);

        var notice = document.createElement('div');
        notice.className = 'notice';
        notice.innerHTML = 'Поля для подписей, инициалов и печатей остаются ' +
            'пустыми — их заполняют от руки после печати документа. ' +
            'Согласие на обработку персональных данных, если оно входит в ' +
            'пакет, также остаётся незаполненным.';
        card.appendChild(notice);

        var list = document.createElement('ul');
        list.className = 'doc-list';
        state.schema.documents.forEach(function (d) {
            var li = document.createElement('li');
            li.textContent = d;
            list.appendChild(li);
        });
        card.appendChild(list);

        var missing = validateAll();
        if (missing.length) {
            var warn = document.createElement('div');
            warn.className = 'notice error';
            warn.style.marginTop = '20px';
            warn.innerHTML = '<strong>Не заполнены обязательные поля:</strong><br>' +
                missing.join('<br>');
            card.appendChild(warn);
        }
        return card;
    }

    function validateStep(step) {
        var bad = [];
        step.fields.forEach(function (f) {
            var err = fieldError(f);
            if (err) { bad.push({ field: f, error: err }); }
        });
        return bad;
    }

    function validateAll() {
        var missing = [];
        state.schema.steps.forEach(function (step, i) {
            validateStep(step).forEach(function (b) {
                missing.push('• ' + b.field.label + ' — ' + b.error +
                    ' (шаг ' + (i + 1) + ': ' + step.title + ')');
            });
        });
        return missing;
    }

    /* -------------------------------------------------------- переходы */

    function next() {
        if (state.step >= state.schema.steps.length) {
            return generate();
        }
        var step = state.schema.steps[state.step];
        var bad = validateStep(step);
        if (bad.length) {
            bad.forEach(function (b) {
                var input = el('fld-' + b.field.key);
                if (!input) { return; }
                input.classList.add('invalid');
                var wrap = input.parentNode;
                if (wrap && !wrap.querySelector('.field-error')) {
                    var msg = document.createElement('div');
                    msg.className = 'field-error';
                    msg.textContent = b.error;
                    wrap.appendChild(msg);
                }
            });
            var first = el('fld-' + bad[0].field.key);
            if (first) {
                first.focus();
                first.scrollIntoView({ block: 'center' });
            }
            return;
        }
        state.step += 1;
        renderStep();
    }

    function prev() {
        if (state.step === 0) {
            show('screen-award');
            return;
        }
        state.step -= 1;
        renderStep();
    }

    /* ------------------------------------------ формирование документов */

    function generate() {
        var missing = validateAll();
        if (missing.length) {
            alert('Не заполнены обязательные поля. Вернитесь к отмеченным шагам.');
            return;
        }

        var payload = JSON.parse(JSON.stringify(state.data));
        payload.work_history = state.history.filter(function (r) {
            return (r.from || r.to || r.position || r.address || '').trim() !== '';
        });

        overlay(true, 'Формируем документы…');
        call('generate', payload).then(function (res) {
            overlay(false);
            if (res.cancelled) { return; }
            if (!res.ok) { return fail(res.error); }

            state.result = res;
            var box = el('done-message');
            box.innerHTML = '';

            var saved = document.createElement('div');
            saved.style.marginBottom = '18px';
            if (res.download) {
                saved.innerHTML = '<strong>Документы готовы.</strong><br>' +
                    'Файл «' + res.filename + '» сейчас скачается — ' +
                    'проверьте папку «Загрузки».';
                // скачивание начинается само
                window.location.href = res.download;
            } else {
                saved.innerHTML = '<strong>Файл сохранён:</strong><br>' + res.path;
            }
            box.appendChild(saved);

            var msg = document.createElement('div');
            msg.textContent = res.message;
            box.appendChild(msg);

            var local = nativeMode() && !res.download;
            el('btn-open-file').classList.toggle('hidden', !local);
            el('btn-open-folder').classList.toggle('hidden', !local);

            show('screen-done');
        }).catch(function (e) { overlay(false); fail(e.message); });
    }

    /* Возврат к анкете после просмотра документа: данные остаются в памяти,
       чтобы поправить опечатку и сформировать пакет заново, а не заполнять
       всё сначала. */
    function backToForm() {
        if (!state.schema) { return; }
        state.step = 0;
        state.result = null;
        renderStep();
        show('screen-form');
    }

    function finish() {
        // персональные данные не сохраняются — очищаем всё
        state.award = null;
        state.status = null;
        state.schema = null;
        state.data = {};
        state.history = [];
        state.result = null;
        state.step = 0;
        el('search-input').value = '';
        document.querySelectorAll('.level-item').forEach(function (l) {
            l.classList.remove('expanded');
        });
        document.querySelectorAll('.award-tile').forEach(function (t) {
            t.classList.remove('highlight');
        });
        show('screen-home');
    }

    function fail(message) {
        alert(message || 'Произошла непредвиденная ошибка.');
    }

    /* ----------------------------------------------------------- запуск */

    function bind() {
        document.querySelectorAll('[data-action="home"]').forEach(function (b) {
            b.addEventListener('click', function () { show('screen-home'); });
        });
        document.querySelectorAll('[data-action="start-form"]').forEach(function (b) {
            b.addEventListener('click', startForm);
        });
        el('btn-next').addEventListener('click', next);
        el('btn-prev').addEventListener('click', prev);
        el('btn-finish').addEventListener('click', finish);
        el('btn-back-form').addEventListener('click', backToForm);
        el('btn-open-file').addEventListener('click', function () {
            if (state.result) { call('open_file', state.result.path); }
        });
        el('btn-open-folder').addEventListener('click', function () {
            if (state.result) { call('open_folder', state.result.path); }
        });
        el('search-input').addEventListener('keypress', function (e) {
            if (e.key === 'Enter') { performSearch(); }
        });
    }

    /* Сообщение вместо списка наград: пока он грузится и если не загрузился.
       Раньше в этом месте была пустота, и по ней нельзя было понять,
       работает программа или замерла. */
    function homeNotice(text, retry) {
        var box = el('levels-container');
        box.innerHTML = '';
        var div = document.createElement('div');
        div.className = 'load-notice';
        div.textContent = text;
        box.appendChild(div);
        if (retry) {
            var btn = document.createElement('button');
            btn.className = 'btn btn-submit';
            btn.textContent = 'Попробовать снова';
            btn.addEventListener('click', function () { loadLevels(); });
            div.appendChild(document.createElement('br'));
            div.appendChild(btn);
        }
    }

    /* Загрузка справочника наград. Вызов идёт ровно один за раз: параллельные
       обращения ничего не ускоряют, а разобраться в происходящем мешают. */
    var loading = false;

    function loadLevels() {
        if (loading) { return; }
        loading = true;
        homeNotice('Загружаем справочник наград…');

        var slow = setTimeout(function () {
            homeNotice('Справочник наград загружается дольше обычного. ' +
                'Подождите ещё немного — программа не зависла.');
        }, 5000);

        call('get_levels').then(function (res) {
            clearTimeout(slow);
            loading = false;
            if (!res.ok) {
                return homeNotice('Не удалось загрузить справочник наград.\n' +
                    (res.error || ''), true);
            }
            state.levels = res.levels;
            state.developer = res.developer === true;
            el('service-badge').classList.toggle('hidden', !state.developer);
            renderHome();
        }).catch(function (e) {
            clearTimeout(slow);
            loading = false;
            homeNotice('Не удалось связаться с программой: ' +
                (e && e.message ? e.message : 'связь потеряна') +
                '\nЗакройте окно и запустите программу заново.', true);
        });
    }

    /* ------------------------------------------- меню правой кнопки */

    /* В окне программы обычное меню браузера отключено, и скопировать текст
       из поля можно было только с клавиатуры. Поэтому меню своё: копировать,
       вырезать, вставить, выделить всё. Вставка идёт через системный буфер
       обмена; если система её не разрешит, подсказываем сочетание клавиш. */

    var ctxMenu = null;
    var ctxTarget = null;

    function editable(node) {
        if (!node || !node.tagName) { return null; }
        var tag = node.tagName.toLowerCase();
        return (tag === 'input' || tag === 'textarea') ? node : null;
    }

    function selectedText(field) {
        if (field) {
            return field.value.substring(field.selectionStart,
                                         field.selectionEnd);
        }
        return String(window.getSelection ? window.getSelection() : '');
    }

    function replaceSelection(field, text) {
        var start = field.selectionStart, end = field.selectionEnd;
        field.value = field.value.substring(0, start) + text +
            field.value.substring(end);
        var pos = start + text.length;
        field.setSelectionRange(pos, pos);
        // сообщаем анкете, что значение изменилось
        var event;
        try {
            event = new Event('input', { bubbles: true });
        } catch (e) {
            event = document.createEvent('Event');
            event.initEvent('input', true, false);
        }
        field.dispatchEvent(event);
    }

    function ctxAction(name) {
        var field = ctxTarget;
        hideContextMenu();
        if (field) { field.focus(); }

        if (name === 'selectAll') {
            if (field) { field.select(); }
            return;
        }
        if (name === 'copy' || name === 'cut') {
            try { document.execCommand(name); } catch (e) { /* не вышло */ }
            return;
        }
        if (name === 'paste') {
            if (!field) { return; }
            if (navigator.clipboard && navigator.clipboard.readText) {
                navigator.clipboard.readText().then(function (text) {
                    if (text) { replaceSelection(field, text); }
                }).catch(function () {
                    alert('Система не разрешила программе прочитать буфер ' +
                        'обмена.\nВставьте текст сочетанием клавиш Ctrl+V.');
                });
            } else {
                alert('Вставьте текст сочетанием клавиш Ctrl+V.');
            }
        }
    }

    function buildContextMenu() {
        ctxMenu = document.createElement('div');
        ctxMenu.className = 'ctx-menu hidden';
        [['copy', 'Копировать'], ['cut', 'Вырезать'],
         ['paste', 'Вставить'], ['selectAll', 'Выделить всё']]
            .forEach(function (item) {
                var el = document.createElement('div');
                el.className = 'ctx-item';
                el.dataset.action = item[0];
                el.textContent = item[1];
                el.addEventListener('mousedown', function (e) {
                    e.preventDefault();          // не терять выделение в поле
                    if (!el.classList.contains('disabled')) {
                        ctxAction(item[0]);
                    }
                });
                ctxMenu.appendChild(el);
            });
        document.body.appendChild(ctxMenu);
    }

    function hideContextMenu() {
        if (ctxMenu) { ctxMenu.classList.add('hidden'); }
    }

    function showContextMenu(e) {
        var field = editable(e.target);
        var selection = selectedText(field);
        if (!field && !selection) { return; }      // нечего предлагать
        e.preventDefault();

        ctxTarget = field;
        ctxMenu.querySelectorAll('.ctx-item').forEach(function (item) {
            var action = item.dataset.action;
            var off = (!selection && (action === 'copy' || action === 'cut')) ||
                (!field && action !== 'copy');
            item.classList.toggle('disabled', off);
            item.classList.toggle('hidden', !field && action !== 'copy');
        });

        ctxMenu.classList.remove('hidden');
        // не даём меню вылезти за край окна
        var w = ctxMenu.offsetWidth, h = ctxMenu.offsetHeight;
        var x = Math.min(e.clientX, window.innerWidth - w - 6);
        var y = Math.min(e.clientY, window.innerHeight - h - 6);
        ctxMenu.style.left = Math.max(4, x) + 'px';
        ctxMenu.style.top = Math.max(4, y) + 'px';
    }

    function bindContextMenu() {
        buildContextMenu();
        document.addEventListener('contextmenu', showContextMenu);
        document.addEventListener('click', hideContextMenu);
        document.addEventListener('scroll', hideContextMenu, true);
        window.addEventListener('blur', hideContextMenu);
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { hideContextMenu(); }
        });
    }

    /* ------------------------------------------------ служебный режим */

    /* Режим снимает ограничение по срокам подачи: без него нельзя проверить
       формирование документов для награды, чей срок ещё не наступил.
       Вызывается пятью быстрыми щелчками по гербу — герб при этом остаётся
       обычной картинкой, ничем не намекающей на скрытую возможность. */
    var TAPS_NEEDED = 5;
    var TAP_WINDOW = 2500;      // мс, за которые нужно уложиться
    var taps = [];

    function noteTap() {
        var now = Date.now();
        taps.push(now);
        taps = taps.filter(function (t) { return now - t <= TAP_WINDOW; });
        if (taps.length >= TAPS_NEEDED) {
            taps = [];
            openServiceDialog();
        }
    }

    function openServiceDialog() {
        var on = state.developer;
        el('service-title').textContent = on
            ? 'Выключить служебный режим'
            : 'Служебный режим';
        el('service-text').textContent = on
            ? 'Ограничение по срокам подачи вернётся: программа снова будет ' +
              'вести себя так, как у обычного пользователя.'
            : 'Ограничение по срокам подачи будет снято — станут доступны ' +
              'все награды, включая те, приём по которым ещё не начался.';
        el('service-error').classList.add('hidden');
        el('service-password').value = '';
        el('service-overlay').classList.remove('hidden');
        el('service-password').focus();
    }

    function closeServiceDialog() {
        el('service-overlay').classList.add('hidden');
        el('service-password').value = '';
    }

    function submitService() {
        var password = el('service-password').value;
        call('toggle_developer', password).then(function (res) {
            if (!res.ok) {
                var err = el('service-error');
                err.textContent = res.error || 'Пароль не подошёл.';
                err.classList.remove('hidden');
                el('service-password').select();
                return;
            }
            closeServiceDialog();
            state.developer = res.developer;
            el('service-badge').classList.toggle('hidden', !res.developer);
            loadLevels();                   // сроки пересчитываются заново
            show('screen-home');
        }).catch(function (e) {
            var err = el('service-error');
            err.textContent = e && e.message ? e.message : 'Не удалось.';
            err.classList.remove('hidden');
        });
    }

    function bindService() {
        var coat = el('coat-of-arms');
        if (coat) { coat.addEventListener('click', noteTap); }
        el('service-ok').addEventListener('click', submitService);
        el('service-cancel').addEventListener('click', closeServiceDialog);
        el('service-password').addEventListener('keypress', function (e) {
            if (e.key === 'Enter') { submitService(); }
        });
    }

    function boot() {
        bind();
        bindService();
        bindContextMenu();
        loadLevels();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
