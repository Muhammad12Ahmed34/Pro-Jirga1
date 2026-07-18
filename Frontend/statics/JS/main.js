// Pro Jirga — minimal vanilla JS
window.ProJirga = (function () {
  function fileDropLabelUpdate() {
    document.querySelectorAll('.file-drop').forEach(function (label) {
      var input = label.querySelector('input[type="file"]');
      if (!input) return;
      input.addEventListener('change', function () {
        if (input.files && input.files[0]) {
          var span = label.querySelector('span:not(.file-icon)');
          if (span) span.textContent = input.files[0].name;
          label.style.borderColor = 'var(--accent)';
          label.style.color = 'var(--accent)';
        }
      });
    });
  }

  function startTimer() {
    var el = document.getElementById('timer');
    var wrapper = document.querySelector('.timer');
    if (!el || !wrapper) return;
    var minutes = parseInt(wrapper.getAttribute('data-minutes'), 10) || 30;
    var seconds = minutes * 60;
    function tick() {
      var m = Math.floor(seconds / 60);
      var s = seconds % 60;
      el.textContent = String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
      if (seconds <= 0) { el.style.color = '#b91c1c'; return; }
      seconds--;
      setTimeout(tick, 1000);
    }
    tick();
  }

  document.addEventListener('DOMContentLoaded', function () {
    fileDropLabelUpdate();
  });

  return { startTimer: startTimer };
})();
