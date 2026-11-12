import { NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { requireApiAuth } from "@/lib/api-auth";
import { canEditPage, canReadPage } from "@/lib/access";
import { makeId } from "@/lib/ids";

type StoredPropertyType = "title" | "text" | "select" | "multi_select" | "checkbox" | "date";
type DisplayPropertyType = StoredPropertyType | "number" | "person" | "email" | "status";

type SelectOption = {
  id: string;
  label: string;
  color: string;
  group?: string;
};

const DISPLAY_PROPERTY_TYPES = new Set<DisplayPropertyType>([
  "title",
  "text",
  "select",
  "multi_select",
  "checkbox",
  "date",
  "number",
  "person",
  "email",
  "status",
]);

function normalizeOption(input: unknown): SelectOption | null {
  if (typeof input === "string") {
    const label = input.trim();
    if (!label) return null;
    return {
      id: makeId("opt"),
      label,
      color: "default",
    };
  }

  if (!input || typeof input !== "object") return null;
  const source = input as {
    id?: unknown;
    label?: unknown;
    name?: unknown;
    color?: unknown;
    group?: unknown;
  };
  const labelRaw = typeof source.label === "string" ? source.label : typeof source.name === "string" ? source.name : "";
  const label = labelRaw.trim();
  if (!label) return null;
  return {
    id: typeof source.id === "string" && source.id.trim() ? source.id.trim() : makeId("opt"),
    label,
    color: typeof source.color === "string" && source.color.trim() ? source.color.trim() : "default",
    group: typeof source.group === "string" && source.group.trim() ? source.group.trim() : undefined,
  };
}

function normalizeOptions(input: unknown): SelectOption[] {
  if (!Array.isArray(input)) return [];
  return input.map(normalizeOption).filter((item): item is SelectOption => Boolean(item));
}

function statusDefaultOptions(): SelectOption[] {
  return [
    { id: makeId("opt"), label: "To-do", color: "gray", group: "To-do" },
    { id: makeId("opt"), label: "In progress", color: "blue", group: "In progress" },
    { id: makeId("opt"), label: "Complete", color: "green", group: "Complete" },
  ];
}

function normalizeDisplayType(input: unknown): DisplayPropertyType {
  if (typeof input !== "string") return "text";
  const normalized = input.trim() as DisplayPropertyType;
  if (!DISPLAY_PROPERTY_TYPES.has(normalized)) return "text";
  return normalized;
}

function toStoredPropertyConfig(displayType: DisplayPropertyType, optionsInput?: unknown) {
  const options = normalizeOptions(optionsInput);
  if (displayType === "status") {
    return {
      type: "select" as StoredPropertyType,
      configJson: {
        subtype: "status",
        options: options.length > 0 ? options : statusDefaultOptions(),
      },
    };
  }
  if (displayType === "person") {
    return {
      type: "multi_select" as StoredPropertyType,
      configJson: {
        subtype: "person",
        options,
      },
    };
  }
  if (displayType === "number") {
    return {
      type: "text" as StoredPropertyType,
      configJson: {
        subtype: "number",
      },
    };
  }
  if (displayType === "email") {
    return {
      type: "text" as StoredPropertyType,
      configJson: {
        subtype: "email",
      },
    };
  }
  if (displayType === "select" || displayType === "multi_select") {
    return {
      type: displayType as StoredPropertyType,
      configJson: {
        options,
      },
    };
  }
  return {
    type: displayType as StoredPropertyType,
    configJson: {},
  };
}

function defaultPropertyName(displayType: DisplayPropertyType) {
  if (displayType === "title") return "Name";
  if (displayType === "multi_select") return "Tags";
  if (displayType === "number") return "Number";
  if (displayType === "person") return "Person";
  if (displayType === "email") return "Email";
  if (displayType === "status") return "Status";
  return displayType.charAt(0).toUpperCase() + displayType.slice(1);
}

async function resolveDatabaseWithPage(id: string, userId: string) {
  return (
    (await prisma.database.findUnique({
      where: { id },
      include: {
        properties: { orderBy: { position: "asc" } },
        page: {
          include: {
            permissions: {
              where: { userId },
            },
          },
        },
      },
    })) ||
    (await prisma.database.findUnique({
      where: { pageId: id },
      include: {
        properties: { orderBy: { position: "asc" } },
        page: {
          include: {
            permissions: {
              where: { userId },
            },
          },
        },
      },
    }))
  );
}

export async function GET(_: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const database = await resolveDatabaseWithPage(params.id, auth.session.userId);

  if (!database) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  if (database.page.deletedAt) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: database.page.workspaceId,
        userId: auth.session.userId,
      },
    },
    select: { role: true },
  });

  const readable = canReadPage({
    accessLevel: database.page.accessLevel,
    workspaceRole: membership?.role ?? null,
    isPageCreator: database.page.createdById === auth.session.userId,
    permissionRole: database.page.permissions[0]?.role,
  });
  if (!readable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  return NextResponse.json({ database });
}

export async function PATCH(request: Request, { params }: { params: { id: string } }) {
  const auth = requireApiAuth();
  if (!auth.ok) return auth.response;

  const database = await resolveDatabaseWithPage(params.id, auth.session.userId);
  if (!database) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (database.page.deletedAt) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const membership = await prisma.workspaceMembership.findUnique({
    where: {
      workspaceId_userId: {
        workspaceId: database.page.workspaceId,
        userId: auth.session.userId,
      },
    },
    select: { role: true },
  });

  const editable = canEditPage({
    accessLevel: database.page.accessLevel,
    workspaceRole: membership?.role ?? null,
    isPageCreator: database.page.createdById === auth.session.userId,
    permissionRole: database.page.permissions[0]?.role,
  });
  if (!editable) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  if (database.page.isLocked) {
    return NextResponse.json({ error: "Page is locked" }, { status: 423 });
  }

  const body = await request.json().catch(() => null);
  const action = body?.action?.toString();

  if (action === "add_property" || action === "insert_property") {
    const displayType = normalizeDisplayType(body?.type);
    const normalized = toStoredPropertyConfig(displayType, body?.options);
    const name =
      typeof body?.name === "string" && body.name.trim() ? body.name.trim() : defaultPropertyName(displayType);

    const referencePropertyId = typeof body?.referencePropertyId === "string" ? body.referencePropertyId : null;
    const side = body?.side === "left" ? "left" : "right";

    const property = await prisma.$transaction(async (tx) => {
      const properties = await tx.databaseProperty.findMany({
        where: { databaseId: database.id },
        orderBy: { position: "asc" },
        select: { id: true, position: true },
      });
      let insertPosition = properties.length;
      if (referencePropertyId) {
        const reference = properties.find((item: { id: string; position: number }) => item.id === referencePropertyId);
        if (reference) {
          insertPosition = side === "left" ? reference.position : reference.position + 1;
        }
      }
      await tx.databaseProperty.updateMany({
        where: { databaseId: database.id, position: { gte: insertPosition } },
        data: { position: { increment: 1 } },
      });
      return tx.databaseProperty.create({
        data: {
          id: makeId("prop"),
          databaseId: database.id,
          name,
          type: normalized.type,
          position: insertPosition,
          configJson: normalized.configJson,
        },
      });
    });
    return NextResponse.json({ property });
  }

  if (action === "duplicate_property") {
    const propertyId = typeof body?.propertyId === "string" ? body.propertyId : "";
    if (!propertyId) {
      return NextResponse.json({ error: "propertyId is required" }, { status: 400 });
    }
    const source = await prisma.databaseProperty.findFirst({
      where: { id: propertyId, databaseId: database.id },
    });
    if (!source) {
      return NextResponse.json({ error: "Property not found" }, { status: 404 });
    }
    if (source.type === "title") {
      return NextResponse.json({ error: "Title property cannot be duplicated" }, { status: 400 });
    }
    const duplicated = await prisma.$transaction(async (tx) => {
      const insertPosition = source.position + 1;
      await tx.databaseProperty.updateMany({
        where: { databaseId: database.id, position: { gte: insertPosition } },
        data: { position: { increment: 1 } },
      });
      return tx.databaseProperty.create({
        data: {
          id: makeId("prop"),
          databaseId: database.id,
          name: `${source.name} copy`,
          type: source.type,
          position: insertPosition,
          configJson: source.configJson ?? {},
        },
      });
    });
    return NextResponse.json({ property: duplicated });
  }

  if (action === "update_property") {
    const propertyId = typeof body?.propertyId === "string" ? body.propertyId : "";
    if (!propertyId) {
      return NextResponse.json({ error: "propertyId is required" }, { status: 400 });
    }
    const property = await prisma.databaseProperty.findFirst({
      where: { id: propertyId, databaseId: database.id },
    });
    if (!property) {
      return NextResponse.json({ error: "Property not found" }, { status: 404 });
    }

    const nextName = typeof body?.name === "string" && body.name.trim() ? body.name.trim() : property.name;
    const wantsTypeChange = typeof body?.type === "string" && body.type.trim().length > 0;
    const displayType = wantsTypeChange ? normalizeDisplayType(body.type) : null;

    if (property.type === "title" && displayType && displayType !== "title") {
      return NextResponse.json({ error: "Title property type cannot be changed" }, { status: 400 });
    }
    if (property.type !== "title" && displayType === "title") {
      return NextResponse.json({ error: "Only one title property is allowed" }, { status: 400 });
    }

    let nextType: StoredPropertyType = property.type as StoredPropertyType;
    let nextConfig: Record<string, unknown> =
      property.configJson && typeof property.configJson === "object"
        ? ({ ...(property.configJson as Record<string, unknown>) } as Record<string, unknown>)
        : {};

    if (displayType) {
      const converted = toStoredPropertyConfig(displayType, body?.options);
      nextType = converted.type;
      nextConfig = converted.configJson as Record<string, unknown>;
    }

    if (Array.isArray(body?.options)) {
      nextConfig = {
        ...nextConfig,
        options: normalizeOptions(body.options),
      };
    }

    if (body?.configJson && typeof body.configJson === "object") {
      nextConfig = {
        ...nextConfig,
        ...(body.configJson as Record<string, unknown>),
      };
    }

    const updated = await prisma.databaseProperty.update({
      where: { id: property.id },
      data: {
        name: nextName,
        type: nextType,
        configJson: nextConfig as Prisma.InputJsonValue,
      },
    });
    return NextResponse.json({ property: updated });
  }

  if (action === "delete_property") {
    const propertyId = typeof body?.propertyId === "string" ? body.propertyId : "";
    if (!propertyId) {
      return NextResponse.json({ error: "propertyId is required" }, { status: 400 });
    }
    const property = await prisma.databaseProperty.findFirst({
      where: { id: propertyId, databaseId: database.id },
      select: { id: true, type: true, position: true },
    });
    if (!property) {
      return NextResponse.json({ error: "Property not found" }, { status: 404 });
    }
    if (property.type === "title") {
      return NextResponse.json({ error: "Title property cannot be deleted" }, { status: 400 });
    }

    await prisma.$transaction(async (tx) => {
      await tx.databaseProperty.delete({ where: { id: property.id } });
      await tx.databaseProperty.updateMany({
        where: {
          databaseId: database.id,
          position: { gt: property.position },
        },
        data: { position: { decrement: 1 } },
      });
    });

    return NextResponse.json({ ok: true });
  }

  if (action === "move_property") {
    const propertyId = typeof body?.propertyId === "string" ? body.propertyId : "";
    const targetIndex = Number.isInteger(body?.targetIndex) ? Number(body.targetIndex) : null;
    if (!propertyId || targetIndex === null) {
      return NextResponse.json({ error: "propertyId and targetIndex are required" }, { status: 400 });
    }
    const properties = await prisma.databaseProperty.findMany({
      where: { databaseId: database.id },
      orderBy: { position: "asc" },
      select: { id: true },
    });
    const sourceIndex = properties.findIndex((item: { id: string }) => item.id === propertyId);
    if (sourceIndex === -1) {
      return NextResponse.json({ error: "Property not found" }, { status: 404 });
    }
    const clamped = Math.max(0, Math.min(properties.length - 1, targetIndex));
    if (clamped !== sourceIndex) {
      const reordered = [...properties];
      const [moved] = reordered.splice(sourceIndex, 1);
      reordered.splice(clamped, 0, moved);
      await prisma.$transaction(
        reordered.map((item: { id: string }, position) =>
          prisma.databaseProperty.update({
            where: { id: item.id },
            data: { position },
          })
        )
      );
    }
    const property = await prisma.databaseProperty.findUnique({ where: { id: propertyId } });
    return NextResponse.json({ property });
  }

  return NextResponse.json({ error: "Unsupported action" }, { status: 400 });
}
