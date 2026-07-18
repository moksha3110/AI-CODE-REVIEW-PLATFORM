"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bell } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { notificationApi } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { relativeTime } from "@/lib/format";
import type { Notification } from "@/lib/types";

export function NotificationsBell() {
  const { accessToken, refreshAccessToken } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const page = await notificationApi.list({ limit: 8 }, accessToken, refreshAccessToken);
      setNotifications(page.items);
      setUnreadCount(page.unread_count);
    } catch {
      // Notification Service being unreachable shouldn't break the rest of
      // the header - the bell just stays quiet.
    }
  }, [accessToken, refreshAccessToken]);

  useEffect(() => {
    // Standard fetch-on-mount: `load` awaits the network call before
    // touching state, so this isn't a synchronous render-time setState -
    // just the well-known "effect fetches, callback sets state" shape the
    // lint rule itself recommends, traced one level too eagerly through
    // the local closure.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) void load();
  };

  const handleClickNotification = async (notification: Notification) => {
    if (!notification.read_at && accessToken) {
      try {
        await notificationApi.markRead(notification.id, accessToken, refreshAccessToken);
        setUnreadCount((count) => Math.max(0, count - 1));
        setNotifications((items) =>
          items.map((item) =>
            item.id === notification.id ? { ...item, read_at: new Date().toISOString() } : item,
          ),
        );
      } catch {
        // Best-effort - the link navigation below still works either way.
      }
    }
  };

  if (!accessToken) return null;

  return (
    <DropdownMenu open={open} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger className="relative rounded-full p-2 hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Notifications</DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        {notifications.length === 0 && (
          <p className="px-2 py-4 text-center text-sm text-muted-foreground">
            No notifications yet
          </p>
        )}
        {notifications.map((notification) => (
          <DropdownMenuItem
            key={notification.id}
            className="flex-col items-start gap-1 whitespace-normal"
            render={
              <Link
                href={`/repositories/${notification.repository_id}`}
                onClick={() => void handleClickNotification(notification)}
              />
            }
          >
            <span className={notification.read_at ? "text-muted-foreground" : "font-medium"}>
              {notification.message}
            </span>
            <span className="text-xs text-muted-foreground">
              {relativeTime(notification.created_at)}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
