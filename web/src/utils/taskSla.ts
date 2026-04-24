import type { TaskSlaSnapshot } from "@/api/taskSla";

export function formatDuration(totalSeconds?: number | null): string {
  if (totalSeconds == null) {
    return "-";
  }
  if (totalSeconds < 60) {
    return `${totalSeconds} 秒`;
  }
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours} 小时 ${minutes} 分`;
  }
  if (minutes > 0) {
    return seconds > 0 ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分`;
  }
  return `${seconds} 秒`;
}

export function slaStatusLabel(status: string): string {
  if (status === "normal") {
    return "正常";
  }
  if (status === "warning") {
    return "预警";
  }
  if (status === "breached") {
    return "超时";
  }
  if (status === "completed") {
    return "已完成";
  }
  if (status === "failed") {
    return "失败";
  }
  return status;
}

export function slaTagType(
  status: string,
): "success" | "warning" | "danger" | "info" {
  if (status === "normal" || status === "completed") {
    return "success";
  }
  if (status === "warning") {
    return "warning";
  }
  if (status === "breached" || status === "failed") {
    return "danger";
  }
  return "info";
}

export function slaClockText(sla?: TaskSlaSnapshot | null): string {
  if (!sla) {
    return "-";
  }
  if (sla.status === "completed") {
    return `完成耗时 ${formatDuration(sla.resolution_seconds)}`;
  }
  if (sla.status === "failed") {
    return `失败耗时 ${formatDuration(sla.resolution_seconds ?? sla.elapsed_seconds)}`;
  }
  if (sla.status === "breached") {
    return `已等待 ${formatDuration(sla.elapsed_seconds)} · 超时 ${formatDuration(sla.breach_seconds)}`;
  }
  return `已等待 ${formatDuration(sla.elapsed_seconds)} · 剩余 ${formatDuration(Math.max(0, sla.remaining_seconds))}`;
}
