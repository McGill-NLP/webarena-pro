import { z } from "zod";

export const contactSchema = z.object({
  firstName: z.string().min(1),
  lastName: z.string().min(1),
  email: z.string().email().optional().or(z.literal("")),
  phone: z.string().optional(),
  jobTitle: z.string().optional(),
  companyId: z.number().int().optional().nullable(),
});

export const companySchema = z.object({
  name: z.string().min(1),
  domain: z.string().optional(),
  industry: z.string().optional(),
  size: z.string().optional(),
  website: z.string().optional(),
  phone: z.string().optional(),
  address: z.string().optional(),
});

export const dealSchema = z.object({
  title: z.string().min(1),
  value: z.number().min(0),
  status: z.enum(["open", "won", "lost"]).default("open"),
  stageId: z.number().int(),
  pipelineId: z.number().int(),
  contactId: z.number().int().optional().nullable(),
  companyId: z.number().int().optional().nullable(),
  expectedCloseDate: z.string().optional().nullable(),
});

export const activitySchema = z.object({
  type: z.enum(["call", "email", "meeting", "task", "deadline", "lunch"]),
  subject: z.string().min(1),
  description: z.string().optional().nullable(),
  dueDate: z.string().optional().nullable(),
  isDone: z.boolean().optional().default(false),
  dealId: z.number().int().optional().nullable(),
  contactId: z.number().int().optional().nullable(),
  companyId: z.number().int().optional().nullable(),
});

export const stageSchema = z.object({
  name: z.string().min(1),
  pipelineId: z.number().int(),
  probability: z.number().int().min(0).max(100).default(0),
  position: z.number().int().min(0).default(0),
});

export const dealReorderSchema = z.object({
  dealId: z.number().int(),
  newStageId: z.number().int(),
  newPosition: z.number().int().min(0),
});
