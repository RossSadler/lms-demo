const lessons = [
  {
    title: "Why Documents Are Not Courses",
    body: `
      A document can contain useful information, but that does not automatically make it a course.
      Learners need structure, pacing, explanation, and clear next steps.

      In a normal document, the reader has to do most of the work. They must find the important points,
      decide what matters, and work out how each section connects to the next.

      A course does that work for them. It breaks the content into focused lessons, gives each lesson a
      purpose, and guides the learner through the material in a controlled order.

      This demo shows how raw source material can be transformed into a guided learning experience with
      lessons, narration, video, and supporting visuals.
    `,
    insight: `
      The goal is not simply to convert text into pages. The goal is to reshape information into something
      a learner can follow, understand, and complete.
    `,
    video: "media/lesson_1_intro.mp4",
    audio: "media/lesson_1_narration.mp3"
  },
  {
    title: "Turning Source Material into Structured Lessons",
    body: `
      Good course design starts by identifying the natural structure inside the source material.

      Long documents usually contain headings, definitions, rules, examples, and repeated ideas.
      The course builder turns those sections into smaller learning units so the learner is not faced with
      one large block of information.

      Each lesson should answer one clear question. What does the learner need to understand here?
      What should they remember? What should they be able to do after this section?

      Once those answers are clear, the document stops feeling like reference material and starts behaving
      like training.
    `,
    insight: `
      A strong course is built from small, purposeful sections. Each lesson should have a single job.
    `,
    video: "",
    audio: ""
  },
  {
    title: "Adding Voice, Video, and Visuals",
    body: `
      Once the lesson structure is in place, media can make the experience easier to follow.

      Narration helps pace the learning and makes the course feel more guided.
      A short presenter video can introduce the topic and give the experience a human front door.
      Supporting visuals can highlight scenarios, decisions, risks, or examples from the lesson.

      The important point is that media should support the learning, not decorate it.
      A useful course visual should clarify the content. A useful video should prepare the learner for what
      they are about to do.

      When text, voice, video, and visuals work together, the final result feels like a complete training product.
    `,
    insight: `
      Media should be purposeful. If it does not help the learner understand the lesson, it does not belong in the course.
    `,
    video: "",
    audio: ""
  }
];

let currentLesson = 0;

const lessonList = document.getElementById("lessonList");
const lessonMeta = document.getElementById("lessonMeta");
const lessonTitle = document.getElementById("lessonTitle");
const lessonBody = document.getElementById("lessonBody");
const scenarioText = document.getElementById("scenarioText");
const progressFill = document.getElementById("progressFill");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");

const mediaPanel = document.getElementById("mediaPanel");
const videoBlock = document.getElementById("videoBlock");
const lessonVideo = document.getElementById("lessonVideo");
const lessonAudio = document.getElementById("lessonAudio");
const audioBlock = document.getElementById("audioBlock");
const playMediaBtn = document.getElementById("playMediaBtn");
const visualBlock = document.getElementById("visualBlock");

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function setMediaSource(mediaElement, src, type) {
  while (mediaElement.firstChild) {
    mediaElement.removeChild(mediaElement.firstChild);
  }

  if (!src) return;

  const source = document.createElement("source");
  source.src = src;
  source.type = type;
  mediaElement.appendChild(source);
  mediaElement.load();
}

function renderLessonList() {
  lessonList.innerHTML = "";

  lessons.forEach((lesson, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = index === currentLesson ? "lesson-nav-item active" : "lesson-nav-item";
    button.innerHTML = `
      <span>Lesson ${index + 1}</span>
      <strong>${lesson.title}</strong>
    `;

    button.addEventListener("click", () => {
      currentLesson = index;
      renderLesson();
    });

    lessonList.appendChild(button);
  });
}

function stopMedia() {
  if (lessonVideo) {
    lessonVideo.pause();
    lessonVideo.currentTime = 0;
  }

  if (lessonAudio) {
    lessonAudio.pause();
    lessonAudio.currentTime = 0;
  }
}

function showManualPlayButton(label) {
  playMediaBtn.textContent = label;
  playMediaBtn.classList.remove("hidden");
}

function hideManualPlayButton() {
  playMediaBtn.classList.add("hidden");
}

function configureMedia(lesson, index) {
  stopMedia();
  hideManualPlayButton();

  const hasVideo = Boolean(lesson.video);
  const hasAudio = Boolean(lesson.audio);

  mediaPanel.classList.toggle("hidden", !hasVideo && !hasAudio);
  videoBlock.classList.toggle("hidden", !hasVideo);
  audioBlock.classList.toggle("hidden", !hasAudio);

  setMediaSource(lessonVideo, lesson.video, "video/mp4");
  setMediaSource(lessonAudio, lesson.audio, "audio/mpeg");

  if (!hasVideo && !hasAudio) return;

  if (index === 0 && hasVideo) {
    const playAttempt = lessonVideo.play();

    if (playAttempt !== undefined) {
      playAttempt.catch(() => {
        showManualPlayButton("Play intro video");
      });
    }
  }
}

function renderLesson() {
  const lesson = lessons[currentLesson];

  lessonMeta.textContent = `Lesson ${currentLesson + 1} of ${lessons.length}`;
  lessonTitle.textContent = lesson.title;
  lessonBody.textContent = cleanText(lesson.body);
  scenarioText.textContent = cleanText(lesson.insight);
  progressFill.style.width = `${((currentLesson + 1) / lessons.length) * 100}%`;

  prevBtn.disabled = currentLesson === 0;
  nextBtn.textContent = currentLesson === lessons.length - 1 ? "Finish course" : "Next lesson";

  configureMedia(lesson, currentLesson);
  renderLessonList();
}

lessonVideo.addEventListener("ended", () => {
  const lesson = lessons[currentLesson];

  if (!lesson.audio) return;

  const playAttempt = lessonAudio.play();

  if (playAttempt !== undefined) {
    playAttempt.catch(() => {
      showManualPlayButton("Play lesson narration");
    });
  }
});

playMediaBtn.addEventListener("click", () => {
  const lesson = lessons[currentLesson];

  if (lessonVideo && lesson.video && !lessonVideo.ended) {
    lessonVideo.play();
    hideManualPlayButton();
    return;
  }

  if (lessonAudio && lesson.audio) {
    lessonAudio.play();
    hideManualPlayButton();
  }
});

prevBtn.addEventListener("click", () => {
  if (currentLesson > 0) {
    currentLesson -= 1;
    renderLesson();
  }
});

nextBtn.addEventListener("click", () => {
  if (currentLesson < lessons.length - 1) {
    currentLesson += 1;
    renderLesson();
  }
});

renderLesson();
