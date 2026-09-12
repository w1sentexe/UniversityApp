import { apiGet } from "../api.js";

export const DAYS = [
  { key: "monday", short: "Пн", title: "Понедельник" },
  { key: "tuesday", short: "Вт", title: "Вторник" },
  { key: "wednesday", short: "Ср", title: "Среда" },
  { key: "thursday", short: "Чт", title: "Четверг" },
  { key: "friday", short: "Пт", title: "Пятница" },
  { key: "saturday", short: "Сб", title: "Суббота" },
];

export const LESSON_TYPES = {
  lecture: "Лекция",
  practice: "Практика",
  lab: "Лабораторная",
  seminar: "Семинар",
  other: "Занятие",
};

const cache = new Map();

export function forgetSchedule(group) {
  if (group) cache.delete(normalizeGroup(group));
  else cache.clear();
}

export async function loadSchedule(group) {
  const key = normalizeGroup(group);
  if (!key) return null;
  if (cache.has(key)) return cache.get(key);

  const response = await apiGet(`/schedule/${encodeURIComponent(key)}`);
  const schedule = normalizeSchedule(response && response.schedule);
  cache.set(key, schedule);
  return schedule;
}

export function hasSubgroups(schedule) {
  return allLessons(schedule).some((lesson) => Array.isArray(lesson.subgroups) && lesson.subgroups.length === 1);
}

export function lessonCount(schedule, week, day, subgroup = 0) {
  return lessonsFor(schedule, week, day, subgroup).length;
}

export function lessonsFor(schedule, week, day, subgroup = 0) {
  const lessons = schedule?.[week]?.[day] || [];
  if (!subgroup) return lessons;
  return lessons.filter((lesson) => {
    if (!Array.isArray(lesson.subgroups) || lesson.subgroups.length === 0) return true;
    return lesson.subgroups.includes(subgroup);
  });
}

export function formatTime(value) {
  if (!value) return "";
  const text = String(value).trim();
  const match = text.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return text;
  return `${match[1].padStart(2, "0")}:${match[2]}`;
}

function normalizeGroup(group) {
  return String(group || "").trim();
}

function normalizeSchedule(schedule) {
  if (!schedule) return null;

  return {
    numerator: normalizeWeek(schedule.numerator),
    denominator: normalizeWeek(schedule.denominator),
  };
}

function normalizeWeek(week) {
  return Object.fromEntries(DAYS.map((day) => [day.key, normalizeDay(week?.[day.key])]));
}

function normalizeDay(day) {
  if (Array.isArray(day)) return day.map(normalizeLesson).filter(Boolean);
  if (day && typeof day === "object" && day.schedule) {
    return Object.values(day.schedule).flat().map(normalizeLesson).filter(Boolean);
  }
  return [];
}

function normalizeLesson(lesson) {
  if (!lesson || typeof lesson !== "object") return null;
  return {
    start_time: lesson.start_time || lesson.startTime || "",
    end_time: lesson.end_time || lesson.endTime || "",
    name: lesson.name || "",
    lesson_type: lesson.lesson_type || lesson.lessonType || "other",
    teacher_name: lesson.teacher_name || lesson.teacherName || "",
    classroom: lesson.classroom || "",
    subgroups: Array.isArray(lesson.subgroups) ? lesson.subgroups.map(Number).filter(Number.isFinite) : [],
  };
}

function allLessons(schedule) {
  if (!schedule) return [];
  return ["numerator", "denominator"].flatMap((week) => DAYS.flatMap((day) => schedule[week]?.[day.key] || []));
}
