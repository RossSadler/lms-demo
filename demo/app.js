const lessons = Array.isArray(window.LESSON_DATA) ? window.LESSON_DATA : [];
let currentIndex = 0;

const lessonList = document.getElementById("lessonList");
const lessonMeta = document.getElementById("lessonMeta");
const lessonTitle = document.getElementById("lessonTitle");
const lessonBody = document.getElementById("lessonBody");
const presenterScript = document.getElementById("presenterScript");
const progressFill = document.getElementById("progressFill");

const videoBlock = document.getElementById("videoBlock");
const lessonVideo = document.getElementById("lessonVideo");

const audioBlock = document.getElementById("audioBlock");
const lessonAudio = document.getElementById("lessonAudio");

const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function nl2br(value) {
  return escapeHtml(value).replace(/\n/g, "<br>");
}

function renderLessonList() {
  lessonList.innerHTML = "";

  lessons.forEach((lesson, index) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = index === currentIndex ? "lesson-item active" : "lesson-item";
    item.innerHTML = `${index + 1}. ${escapeHtml(lesson.lesson_title || `Lesson ${index + 1}`)}`;

    item.addEventListener("click", () => {
      currentIndex = index;
      render();
    });

    lessonList.appendChild(item);
  });
}

function renderMedia(lesson) {
  if (lesson.video) {
    lessonVideo.src = lesson.video;
    videoBlock.classList.remove("hidden");
  } else {
    lessonVideo.pause();
    lessonVideo.removeAttribute("src");
    lessonVideo.load();
    videoBlock.classList.add("hidden");
  }

  if (lesson.audio) {
    lessonAudio.src = lesson.audio;
    audioBlock.classList.remove("hidden");
  } else {
    lessonAudio.pause();
    lessonAudio.removeAttribute("src");
    lessonAudio.load();
    audioBlock.classList.add("hidden");
  }
}

function render() {
  if (!lessons.length) {
    lessonMeta.textContent = "No lessons available";
    lessonTitle.textContent = "No lesson data found";
    lessonBody.innerHTML = "";
    presenterScript.innerHTML = "";
    progressFill.style.width = "0%";
    prevBtn.disabled = true;
    nextBtn.disabled = true;
    return;
  }

  const lesson = lessons[currentIndex];

  lessonMeta.textContent = `Lesson ${currentIndex + 1} of ${lessons.length}`;
  lessonTitle.textContent = lesson.lesson_title || `Lesson ${currentIndex + 1}`;
  lessonBody.innerHTML = `<p>${nl2br(lesson.lesson_body || "")}</p>`;
  presenterScript.innerHTML = nl2br(lesson.presenter_script || "");

  const progress = ((currentIndex + 1) / lessons.length) * 100;
  progressFill.style.width = `${progress}%`;

  prevBtn.disabled = currentIndex === 0;
  nextBtn.disabled = currentIndex === lessons.length - 1;

  renderLessonList();
  renderMedia(lesson);
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