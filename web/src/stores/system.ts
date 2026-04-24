import { defineStore } from "pinia";

import {
  fetchSystemOverview,
  runSystemMaintenance,
  type SystemMaintenanceRequest,
  type SystemMaintenanceResult,
  type SystemOverview,
} from "@/api/system";

interface SystemState {
  overview: SystemOverview | null;
  loadingOverview: boolean;
  runningMaintenance: boolean;
  overviewError: string | null;
  maintenanceError: string | null;
  lastMaintenanceResult: SystemMaintenanceResult | null;
}

export const useSystemStore = defineStore("system", {
  state: (): SystemState => ({
    overview: null,
    loadingOverview: false,
    runningMaintenance: false,
    overviewError: null,
    maintenanceError: null,
    lastMaintenanceResult: null,
  }),
  actions: {
    async loadOverview() {
      this.loadingOverview = true;
      this.overviewError = null;

      try {
        this.overview = await fetchSystemOverview();
      } catch (error) {
        this.overviewError =
          error instanceof Error ? error.message : "系统概览加载失败。";
      } finally {
        this.loadingOverview = false;
      }
    },
    async runMaintenance(payload: SystemMaintenanceRequest) {
      this.runningMaintenance = true;
      this.maintenanceError = null;
      try {
        this.lastMaintenanceResult = await runSystemMaintenance(payload);
        return this.lastMaintenanceResult;
      } catch (error) {
        this.maintenanceError =
          error instanceof Error ? error.message : "系统维护执行失败。";
        throw error;
      } finally {
        this.runningMaintenance = false;
      }
    },
  },
});
