"use client";

import { Capacitor } from "@capacitor/core";
import { BiometricAuth } from "@aparajita/capacitor-biometric-auth";
import { CapacitorPersistentAccount } from "@capgo/capacitor-persistent-account";

const SESSION_KEY = "sstore-native-session";

export type NativeSession = {
  token: string;
  username: string;
};

let nativeSession: NativeSession | null = null;

export function isNativeAndroid() {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === "android";
}
export function nativeSessionToken() {
  return nativeSession?.token ?? null;
}

export async function restoreNativeSession() {
  if (!isNativeAndroid()) return null;
  const result = await CapacitorPersistentAccount.readAccount();
  const data = result.data as { [SESSION_KEY]?: NativeSession } | null;
  nativeSession = data?.[SESSION_KEY] ?? null;
  return nativeSession;
}

export async function saveNativeSession(session: NativeSession) {
  nativeSession = session;
  await CapacitorPersistentAccount.saveAccount({ data: { [SESSION_KEY]: session } });
}

export async function clearNativeSession() {
  nativeSession = null;
  await CapacitorPersistentAccount.saveAccount({ data: {} });
}

export async function authenticateNativeSession() {
  if (!isNativeAndroid()) return;
  const availability = await BiometricAuth.checkBiometry();
  if (!availability.isAvailable && !availability.deviceIsSecure) {
    throw new Error("กรุณาตั้งค่าลายนิ้วมือ ใบหน้า หรือรหัสล็อกหน้าจอของ Android ก่อน")
  }
  await BiometricAuth.authenticate({
    reason: "ยืนยันตัวตนเพื่อเปิด SStore",
    cancelTitle: "ยกเลิก",
    allowDeviceCredential: true,
    androidTitle: "ปลดล็อก SStore",
    androidSubtitle: "ใช้ลายนิ้วมือ ใบหน้า หรือรหัสล็อกเครื่อง",
    androidConfirmationRequired: false,
  });
}
