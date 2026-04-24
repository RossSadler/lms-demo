const lessons = Array.isArray(window.LESSON_DATA) ? window.LESSON_DATA : [];
let currentIndex = 0;

const lessonList = document.getElementById("lessonList");
const lessonMeta = document.getElementById("lessonMeta");
const lessonTitle = document.getElementById("lessonTitle");
const lessonBody = document.getElementById("lessonBody");
const progressFill = document.getElementById("progressFill");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");

const imageBlock = document.getElementById("imageBlock");
const lessonImage = document.getElementById("lessonImage");

const audioBlock = document.getElementById("audioBlock");
const lessonAudio = document.getElementById("lessonAudio");

const videoBlock = document.getElementById("videoBlock");
const lessonVideo = document.getElementById("lessonVideo");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function paragraphise(text) {
  const chunks = String(text || "")
    .split(/\n{2,}/)
    .map((chunk) => chunk.trim())
    .filter(Boolean);

  if (!chunks.length) {
    return "<p>No lesson content was generated for this item.</p>";
  }

  return chunks
    .map((chunk) => `<p>${escapeHtml(chunk).replaceAll("\n", "<br>")}</p>`)
    .join("");
}

function renderLessonList() {
  lessonList.innerHTML = "";

  if (!lessons.length) {
    lessonList.innerHTML = '<p class="lesson-empty">No lessons available.</p>';
    return;
  }

  lessons.forEach((lesson, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lesson-item";

    if (index === currentIndex) {
      button.classList.add("active");
    }

    const number = lesson.lesson_number || index + 1;
    const title = lesson.lesson_title || `Lesson ${number}`;
    button.textContent = `${number}. ${title}`;

    button.addEventListener("click", () => {
      currentIndex = index;
      render();
    });

    lessonList.appendChild(button);
  });
}

function renderMedia(lesson) {
  if (lesson.video) {
    lessonVideo.src = lesson.video;
    videoBlock.classList.remove("hidden");
  } else {
    lessonVideo.removeAttribute("src");
    videoBlock.classList.add("hidden");
  }

  if (lesson.image) {
    lessonImage.src = lesson.image;
    lessonImage.alt = lesson.lesson_title ? `Visual for ${lesson.lesson_title}` : "Lesson visual";
    imageBlock.classList.remove("hidden");
  } else {
    lessonImage.removeAttribute("src");
    imageBlock.classList.add("hidden");
  }

  if (lesson.audio) {
    lessonAudio.src = lesson.audio;
    audioBlock.classList.remove("hidden");
  } else {
    lessonAudio.removeAttribute("src");
    audioBlock.classList.add("hidden");
  }
}

function render() {
  if (!lessons.length) {
    lessonMeta.textContent = "No lessons";
    lessonTitle.textContent = "No lesson data available";
    lessonBody.innerHTML = "<p>The course package did not include lesson data.</p>";
    progressFill.style.width = "0%";
    prevBtn.disabled = true;
    nextBtn.disabled = true;
    return;
  }

  const lesson = lessons[currentIndex] || {};
  const total = lessons.length;
  const current = currentIndex + 1;
  const progress = Math.round((current / total) * 100);

  lessonMeta.textContent = `Lesson ${current} of ${total}`;
  lessonTitle.textContent = lesson.lesson_title || `Lesson ${current}`;
  lessonBody.innerHTML = paragraphise(lesson.lesson_body);
  progressFill.style.width = `${progress}%`;

  prevBtn.disabled = currentIndex === 0;
  nextBtn.disabled = currentIndex >= total - 1;

  renderMedia(lesson);
  renderLessonList();
}

prevBtn.addEventListener("click", () => {
  if (currentIndex > 0) {
    currentIndex -= 1;
    render();
  }
});

nextBtn.addEventListener("click", () => {
  if (currentIndex < lessons.length - 1) {
    currentIndex += 1;
    render();
  }
});

render();
