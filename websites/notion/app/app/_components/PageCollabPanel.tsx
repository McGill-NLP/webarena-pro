"use client";

import { useEffect, useState } from "react";

type PermissionItem = {
  id: string;
  role: "editor" | "commenter" | "viewer";
  user: { id: string; email: string };
};

type MemberItem = {
  user: { id: string; email: string };
};

type CommentItem = {
  id: string;
  content: string;
  createdAt: string;
  author: { id: string; email: string };
  mentions: { id: string; user: { id: string; email: string } }[];
};

type ShareLinkItem = {
  id: string;
  token: string;
  isActive: boolean;
  expiresAt: string | null;
};

type AttachmentItem = {
  id: string;
  fileName: string;
  fileUrl: string;
  mimeType: string;
  sizeBytes: number;
};

export default function PageCollabPanel({ pageId }: { pageId: string }) {
  const [permissions, setPermissions] = useState<PermissionItem[]>([]);
  const [members, setMembers] = useState<MemberItem[]>([]);
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [shareLinks, setShareLinks] = useState<ShareLinkItem[]>([]);
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);

  const [commentInput, setCommentInput] = useState("");
  const [permissionUserId, setPermissionUserId] = useState("");
  const [permissionRole, setPermissionRole] = useState<"editor" | "commenter" | "viewer">("viewer");
  const [attachmentUrl, setAttachmentUrl] = useState("");
  const [attachmentName, setAttachmentName] = useState("");

  async function refresh() {
    const [permissionsRes, commentsRes, sharesRes, attachmentsRes] = await Promise.all([
      fetch(`/api/pages/${pageId}/permissions`),
      fetch(`/api/pages/${pageId}/comments`),
      fetch(`/api/pages/${pageId}/share-links`),
      fetch(`/api/pages/${pageId}/attachments`),
    ]);

    if (permissionsRes.ok) {
      const data = await permissionsRes.json();
      setPermissions(data.permissions ?? []);
      setMembers(data.members ?? []);
      if (!permissionUserId && data.members?.length) {
        setPermissionUserId(data.members[0].user.id);
      }
    }

    if (commentsRes.ok) {
      const data = await commentsRes.json();
      setComments(data.comments ?? []);
    }

    if (sharesRes.ok) {
      const data = await sharesRes.json();
      setShareLinks(data.shareLinks ?? []);
    }

    if (attachmentsRes.ok) {
      const data = await attachmentsRes.json();
      setAttachments(data.attachments ?? []);
    }
  }

  useEffect(() => {
    refresh();
  }, [pageId]);

  async function addComment() {
    if (!commentInput.trim()) return;
    await fetch(`/api/pages/${pageId}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: commentInput }),
    });
    setCommentInput("");
    refresh();
  }

  async function addPermission() {
    if (!permissionUserId) return;
    await fetch(`/api/pages/${pageId}/permissions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId: permissionUserId, role: permissionRole }),
    });
    refresh();
  }

  async function removePermission(userId: string) {
    await fetch(`/api/pages/${pageId}/permissions`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId }),
    });
    refresh();
  }

  async function createShareLink() {
    await fetch(`/api/pages/${pageId}/share-links`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    refresh();
  }

  async function toggleShareLink(link: ShareLinkItem) {
    await fetch(`/api/pages/${pageId}/share-links`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shareLinkId: link.id, isActive: !link.isActive }),
    });
    refresh();
  }

  async function addAttachmentByUrl() {
    if (!attachmentUrl.trim()) return;
    await fetch(`/api/pages/${pageId}/attachments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fileName: attachmentName.trim() || "attachment",
        fileUrl: attachmentUrl.trim(),
        mimeType: "application/octet-stream",
        sizeBytes: 0,
      }),
    });
    setAttachmentName("");
    setAttachmentUrl("");
    refresh();
  }

  async function uploadAttachment(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    await fetch(`/api/pages/${pageId}/attachments`, {
      method: "POST",
      body: formData,
    });
    refresh();
  }

  return (
    <section className="mt-8 space-y-4 rounded-lg border border-[var(--line)] bg-[#fafafa] p-4">
      <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">Collaboration</h2>

      <div className="space-y-2 rounded-md border border-[var(--line)] bg-white p-3">
        <p className="text-sm font-medium">Comments</p>
        <div className="flex gap-2">
          <input
            value={commentInput}
            onChange={(event) => setCommentInput(event.target.value)}
            placeholder="Write a comment. Use @email for mention"
            className="flex-1 rounded border border-[var(--line)] px-2 py-1.5 text-sm"
          />
          <button onClick={addComment} className="rounded border border-[var(--line)] px-2 py-1.5 text-sm hover:bg-[var(--hover)]">
            Send
          </button>
        </div>
        <div className="space-y-2">
          {comments.map((comment) => (
            <div key={comment.id} className="rounded border border-[var(--line)] p-2 text-sm">
              <p className="text-xs text-[var(--muted)]">{comment.author.email}</p>
              <p>{comment.content}</p>
              {comment.mentions.length > 0 ? (
                <p className="mt-1 text-xs text-[var(--muted)]">Mentions: {comment.mentions.map((mention) => mention.user.email).join(", ")}</p>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-2 rounded-md border border-[var(--line)] bg-white p-3">
        <p className="text-sm font-medium">Permissions</p>
        <div className="flex flex-wrap gap-2">
          <select value={permissionUserId} onChange={(event) => setPermissionUserId(event.target.value)} className="rounded border border-[var(--line)] px-2 py-1 text-sm">
            {members.map((member) => (
              <option key={member.user.id} value={member.user.id}>
                {member.user.email}
              </option>
            ))}
          </select>
          <select value={permissionRole} onChange={(event) => setPermissionRole(event.target.value as "editor" | "commenter" | "viewer")} className="rounded border border-[var(--line)] px-2 py-1 text-sm">
            <option value="editor">editor</option>
            <option value="commenter">commenter</option>
            <option value="viewer">viewer</option>
          </select>
          <button onClick={addPermission} className="rounded border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]">
            Set
          </button>
        </div>
        <div className="space-y-1">
          {permissions.map((permission) => (
            <div key={permission.id} className="flex items-center justify-between rounded border border-[var(--line)] px-2 py-1 text-sm">
              <span>{permission.user.email} ({permission.role})</span>
              <button onClick={() => removePermission(permission.user.id)} className="text-xs text-[var(--muted)] hover:text-[#b42318]">
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-2 rounded-md border border-[var(--line)] bg-white p-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Share links</p>
          <button onClick={createShareLink} className="rounded border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]">
            New link
          </button>
        </div>
        <div className="space-y-1">
          {shareLinks.map((link) => {
            const url = `${typeof window !== "undefined" ? window.location.origin : ""}/share/${link.token}`;
            return (
              <div key={link.id} className="rounded border border-[var(--line)] px-2 py-1 text-sm">
                <a href={url} target="_blank" rel="noreferrer" className="text-[var(--blue)] underline">
                  {`/share/${link.token}`}
                </a>
                <div className="mt-1 flex items-center justify-between text-xs text-[var(--muted)]">
                  <span>{link.isActive ? "active" : "inactive"}</span>
                  <button onClick={() => toggleShareLink(link)} className="hover:text-[var(--text)]">
                    toggle
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="space-y-2 rounded-md border border-[var(--line)] bg-white p-3">
        <p className="text-sm font-medium">Attachments</p>
        <div className="flex flex-wrap gap-2">
          <input
            value={attachmentName}
            onChange={(event) => setAttachmentName(event.target.value)}
            placeholder="Name"
            className="rounded border border-[var(--line)] px-2 py-1 text-sm"
          />
          <input
            value={attachmentUrl}
            onChange={(event) => setAttachmentUrl(event.target.value)}
            placeholder="File URL"
            className="min-w-[220px] flex-1 rounded border border-[var(--line)] px-2 py-1 text-sm"
          />
          <button onClick={addAttachmentByUrl} className="rounded border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]">
            Add URL
          </button>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]">
          <span>Upload file</span>
          <input
            type="file"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) uploadAttachment(file);
              event.currentTarget.value = "";
            }}
          />
        </label>
        <div className="space-y-1">
          {attachments.map((attachment) => (
            <a key={attachment.id} href={attachment.fileUrl} target="_blank" rel="noreferrer" className="block rounded border border-[var(--line)] px-2 py-1 text-sm hover:bg-[var(--hover)]">
              {attachment.fileName}
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
