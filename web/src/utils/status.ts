export function reviewStatusLabel(status: string): string {
  if (status === "pending") {
    return "待审核";
  }
  if (status === "escalated") {
    return "已升级";
  }
  if (status === "approved") {
    return "已通过";
  }
  if (status === "rejected") {
    return "已驳回";
  }
  return status;
}

export function reviewStatusTagType(
  status: string,
): "warning" | "success" | "danger" | "info" {
  if (status === "pending") {
    return "warning";
  }
  if (status === "escalated") {
    return "danger";
  }
  if (status === "approved") {
    return "success";
  }
  if (status === "rejected") {
    return "danger";
  }
  return "info";
}

export function auditLevelTagType(
  level: string,
): "success" | "warning" | "danger" | "info" {
  if (level === "error") {
    return "danger";
  }
  if (level === "warning") {
    return "warning";
  }
  if (level === "info") {
    return "success";
  }
  return "info";
}
