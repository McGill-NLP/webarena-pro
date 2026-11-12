import { sqliteTable, integer, text, real } from "drizzle-orm/sqlite-core";

export const users = sqliteTable("users", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  email: text("email").notNull().unique(),
  password: text("password").notNull(),
  name: text("name").notNull(),
  createdAt: text("created_at").notNull(),
});

export const companies = sqliteTable("companies", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  userId: integer("user_id").notNull(),
  name: text("name").notNull(),
  domain: text("domain"),
  industry: text("industry"),
  size: text("size"),
  website: text("website"),
  phone: text("phone"),
  address: text("address"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const contacts = sqliteTable("contacts", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  userId: integer("user_id").notNull(),
  companyId: integer("company_id"),
  firstName: text("first_name").notNull(),
  lastName: text("last_name").notNull(),
  email: text("email"),
  phone: text("phone"),
  jobTitle: text("job_title"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const pipelines = sqliteTable("pipelines", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  userId: integer("user_id").notNull(),
  name: text("name").notNull(),
  createdAt: text("created_at").notNull(),
});

export const pipelineStages = sqliteTable("pipeline_stages", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  pipelineId: integer("pipeline_id").notNull(),
  name: text("name").notNull(),
  probability: integer("probability").notNull().default(0),
  position: integer("position").notNull().default(0),
  createdAt: text("created_at").notNull(),
});

export const deals = sqliteTable("deals", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  userId: integer("user_id").notNull(),
  pipelineId: integer("pipeline_id").notNull(),
  stageId: integer("stage_id").notNull(),
  contactId: integer("contact_id"),
  companyId: integer("company_id"),
  title: text("title").notNull(),
  value: real("value").notNull().default(0),
  status: text("status").notNull().default("open"),
  position: integer("position").notNull().default(0),
  expectedCloseDate: text("expected_close_date"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const activities = sqliteTable("activities", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  userId: integer("user_id").notNull(),
  dealId: integer("deal_id"),
  contactId: integer("contact_id"),
  companyId: integer("company_id"),
  type: text("type").notNull(),
  subject: text("subject").notNull(),
  description: text("description"),
  dueDate: text("due_date"),
  isDone: integer("is_done", { mode: "boolean" }).notNull().default(false),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});
