/**
 * ERPNext HR Tools
 *
 * MCP tools for human resources: employees, attendance, leave applications.
 *
 * @module lib/erpnext/tools/hr
 */

import type { FrappeFilter } from "../api/types.ts";
import type { ErpNextTool } from "./types.ts";
import { DOC_META, DOCLIST_META } from "./viewer-meta.ts";
import { resolveEmployee, resolveLink } from "../api/resolve.ts";

export const hrTools: ErpNextTool[] = [
  // ── Employees ─────────────────────────────────────────────────────────────

  {
    name: "erpnext_employee_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description: "List Employees. Filterable by department, status. " +
      "Fields: name, employee_name, designation, department, company, status, date_of_joining.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 20)" },
        department: { type: "string", description: "Filter by department" },
        status: {
          type: "string",
          description: "Filter by status (Active, Inactive, Suspended, Left)",
          enum: ["Active", "Inactive", "Suspended", "Left"],
        },
        company: { type: "string", description: "Filter by company" },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 20;
      const filters: FrappeFilter[] = [];
      if (input.department) {
        filters.push(["department", "=", input.department as string]);
      }
      if (input.status) {
        filters.push(["status", "=", input.status as string]);
      }
      if (input.company) {
        filters.push(["company", "=", input.company as string]);
      }

      const docs = await ctx.client.list("Employee", {
        fields: [
          "name",
          "employee_name",
          "designation",
          "department",
          "company",
          "status",
          "date_of_joining",
        ],
        filters,
        limit,
        order_by: "modified desc",
      });

      return {
        doctype: "Employee",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  {
    name: "erpnext_employee_get",
    annotations: { readOnlyHint: true },
    _meta: DOC_META,
    description:
      "Get a single Employee by name/ID (e.g. HR-EMP-00001). Returns all fields.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description:
            "Employee name or ID (e.g. HR-EMP-00001) — a unique name resolves automatically",
        },
      },
      required: ["name"],
    },
    handler: async (input, ctx) => {
      if (!input.name) {
        throw new Error("[erpnext_employee_get] 'name' is required");
      }
      // The description promises a name works, so resolve it. Strict mode even
      // on this read path: two employees sharing a display name should surface
      // both IDs rather than have one silently picked.
      const employeeId = await resolveLink(
        ctx.client,
        "Employee",
        input.name as string,
        "employee_name",
        { allowPartialMatch: false, inputPath: "name" },
      );
      const doc = await ctx.client.get("Employee", employeeId);
      return { data: { ...doc, doctype: "Employee" } };
    },
  },

  // ── Attendance ────────────────────────────────────────────────────────────

  {
    name: "erpnext_attendance_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description:
      "List Attendance records. Filterable by employee, date range. " +
      "Fields: name, employee, employee_name, attendance_date, status.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 20)" },
        employee: {
          type: "string",
          description:
            "Filter by employee ID or name (e.g. 'HR-EMP-00001' or 'John Doe')",
        },
        status: {
          type: "string",
          description: "Filter by status (Present, Absent, Half Day, On Leave)",
          enum: ["Present", "Absent", "Half Day", "On Leave"],
        },
        date_from: {
          type: "string",
          description: "Start date filter YYYY-MM-DD",
        },
        date_to: { type: "string", description: "End date filter YYYY-MM-DD" },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 20;
      const filters: FrappeFilter[] = [];
      if (input.employee) {
        filters.push([
          "employee",
          "=",
          await resolveEmployee(ctx.client, input.employee as string, {
            inputPath: "employee",
          }),
        ]);
      }
      if (input.status) {
        filters.push(["status", "=", input.status as string]);
      }
      if (input.date_from) {
        filters.push(["attendance_date", ">=", input.date_from as string]);
      }
      if (input.date_to) {
        filters.push(["attendance_date", "<=", input.date_to as string]);
      }

      const docs = await ctx.client.list("Attendance", {
        fields: [
          "name",
          "employee",
          "employee_name",
          "attendance_date",
          "status",
        ],
        filters,
        limit,
        order_by: "attendance_date desc",
      });

      return {
        doctype: "Attendance",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  // ── Leave Applications ────────────────────────────────────────────────────

  {
    name: "erpnext_leave_application_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description:
      "List Leave Applications. Filterable by employee, status, leave_type. " +
      "Fields: name, employee, employee_name, leave_type, from_date, to_date, status.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 20)" },
        employee: {
          type: "string",
          description:
            "Filter by employee ID or name (e.g. 'HR-EMP-00001' or 'John Doe')",
        },
        status: {
          type: "string",
          description: "Filter by status (Open, Approved, Rejected, Cancelled)",
          enum: ["Open", "Approved", "Rejected", "Cancelled"],
        },
        leave_type: {
          type: "string",
          description: "Filter by leave type (e.g. Sick Leave)",
        },
        date_from: {
          type: "string",
          description: "Start date filter YYYY-MM-DD",
        },
        date_to: { type: "string", description: "End date filter YYYY-MM-DD" },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 20;
      const filters: FrappeFilter[] = [];
      if (input.employee) {
        filters.push([
          "employee",
          "=",
          await resolveEmployee(ctx.client, input.employee as string, {
            inputPath: "employee",
          }),
        ]);
      }
      if (input.status) {
        filters.push(["status", "=", input.status as string]);
      }
      if (input.leave_type) {
        filters.push(["leave_type", "=", input.leave_type as string]);
      }
      if (input.date_from) {
        filters.push(["from_date", ">=", input.date_from as string]);
      }
      if (input.date_to) {
        filters.push(["to_date", "<=", input.date_to as string]);
      }

      const docs = await ctx.client.list("Leave Application", {
        fields: [
          "name",
          "employee",
          "employee_name",
          "leave_type",
          "from_date",
          "to_date",
          "status",
        ],
        filters,
        limit,
        order_by: "modified desc",
      });

      return {
        doctype: "Leave Application",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  {
    name: "erpnext_leave_application_get",
    annotations: { readOnlyHint: true },
    _meta: DOC_META,
    description:
      "Get a single Leave Application by name. Returns full document.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Leave Application name" },
      },
      required: ["name"],
    },
    handler: async (input, ctx) => {
      if (!input.name) {
        throw new Error("[erpnext_leave_application_get] 'name' is required");
      }
      const doc = await ctx.client.get(
        "Leave Application",
        input.name as string,
      );
      return { data: { ...doc, doctype: "Leave Application" } };
    },
  },

  {
    name: "erpnext_leave_application_create",
    description:
      "Create a new Leave Application. Requires employee, leave_type, from_date, to_date. " +
      "Dates in YYYY-MM-DD format.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        employee: {
          type: "string",
          description:
            "Employee name or ID (e.g. HR-EMP-00001) — a unique name resolves automatically",
        },
        leave_type: {
          type: "string",
          description: "Leave type (e.g. Sick Leave, Casual Leave)",
        },
        from_date: { type: "string", description: "Start date YYYY-MM-DD" },
        to_date: { type: "string", description: "End date YYYY-MM-DD" },
        reason: { type: "string", description: "Reason for leave (optional)" },
      },
      required: ["employee", "leave_type", "from_date", "to_date"],
    },
    handler: async (input, ctx) => {
      if (!input.employee) {
        throw new Error(
          "[erpnext_leave_application_create] 'employee' is required",
        );
      }
      if (!input.leave_type) {
        throw new Error(
          "[erpnext_leave_application_create] 'leave_type' is required",
        );
      }
      if (!input.from_date) {
        throw new Error(
          "[erpnext_leave_application_create] 'from_date' is required",
        );
      }
      if (!input.to_date) {
        throw new Error(
          "[erpnext_leave_application_create] 'to_date' is required",
        );
      }

      const data: Record<string, unknown> = {
        employee: await resolveLink(
          ctx.client,
          "Employee",
          input.employee as string,
          "employee_name",
          // Write path — see purchasing.ts: no fuzzy matching on writes.
          { allowPartialMatch: false, inputPath: "employee" },
        ),
        leave_type: input.leave_type as string,
        from_date: input.from_date as string,
        to_date: input.to_date as string,
      };
      if (input.reason) {
        data.reason = input.reason as string;
      }

      const doc = await ctx.client.create("Leave Application", data);
      return {
        data: doc,
        message: `Leave Application ${doc.name} created successfully`,
      };
    },
  },

  // ── Salary Slips ──────────────────────────────────────────────────────────

  {
    name: "erpnext_salary_slip_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description:
      "List Salary Slips. Filterable by employee, status, date range. " +
      "Fields: name, employee, employee_name, posting_date, start_date, end_date, gross_pay, net_pay, status.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 20)" },
        employee: {
          type: "string",
          description:
            "Filter by employee ID or name (e.g. 'HR-EMP-00001' or 'John Doe')",
        },
        status: {
          type: "string",
          description: "Filter by status (Draft, Submitted, Cancelled)",
          enum: ["Draft", "Submitted", "Cancelled"],
        },
        date_from: {
          type: "string",
          description: "Start date filter YYYY-MM-DD (posting_date >=)",
        },
        date_to: {
          type: "string",
          description: "End date filter YYYY-MM-DD (posting_date <=)",
        },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 20;
      const filters: FrappeFilter[] = [];
      if (input.employee) {
        filters.push([
          "employee",
          "=",
          await resolveEmployee(ctx.client, input.employee as string, {
            inputPath: "employee",
          }),
        ]);
      }
      if (input.status) {
        filters.push(["status", "=", input.status as string]);
      }
      if (input.date_from) {
        filters.push(["posting_date", ">=", input.date_from as string]);
      }
      if (input.date_to) {
        filters.push(["posting_date", "<=", input.date_to as string]);
      }

      const docs = await ctx.client.list("Salary Slip", {
        fields: [
          "name",
          "employee",
          "employee_name",
          "posting_date",
          "start_date",
          "end_date",
          "gross_pay",
          "net_pay",
          "status",
        ],
        filters,
        limit,
        order_by: "posting_date desc",
      });

      return {
        doctype: "Salary Slip",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  {
    name: "erpnext_salary_slip_get",
    annotations: { readOnlyHint: true },
    _meta: DOC_META,
    description:
      "Get a single Salary Slip by name/ID. Returns all fields including earnings and deductions.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Salary Slip ID (e.g. Salary Slip/HR-EMP-00001/00001)",
        },
      },
      required: ["name"],
    },
    handler: async (input, ctx) => {
      if (!input.name) {
        throw new Error("[erpnext_salary_slip_get] 'name' is required");
      }
      const doc = await ctx.client.get("Salary Slip", input.name as string);
      return { data: { ...doc, doctype: "Salary Slip" } };
    },
  },

  // ── Payroll Entries ───────────────────────────────────────────────────────

  {
    name: "erpnext_payroll_entry_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description: "List Payroll Entries. Filterable by company, status. " +
      "Fields: name, company, posting_date, payroll_frequency, status.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 20)" },
        company: { type: "string", description: "Filter by company" },
        status: {
          type: "string",
          description: "Filter by status (Draft, Submitted, Cancelled)",
          enum: ["Draft", "Submitted", "Cancelled"],
        },
        date_from: {
          type: "string",
          description: "Start date filter YYYY-MM-DD",
        },
        date_to: { type: "string", description: "End date filter YYYY-MM-DD" },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 20;
      const filters: FrappeFilter[] = [];
      if (input.company) {
        filters.push(["company", "=", input.company as string]);
      }
      if (input.status) {
        filters.push(["status", "=", input.status as string]);
      }
      if (input.date_from) {
        filters.push(["posting_date", ">=", input.date_from as string]);
      }
      if (input.date_to) {
        filters.push(["posting_date", "<=", input.date_to as string]);
      }

      const docs = await ctx.client.list("Payroll Entry", {
        fields: [
          "name",
          "company",
          "posting_date",
          "payroll_frequency",
          "status",
        ],
        filters,
        limit,
        order_by: "posting_date desc",
      });

      return {
        doctype: "Payroll Entry",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  // ── Expense Claims ────────────────────────────────────────────────────────

  {
    name: "erpnext_expense_claim_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description:
      "List Expense Claims. Filterable by employee, status, approval_status. " +
      "Fields: name, employee, employee_name, posting_date, total_claimed_amount, status, approval_status.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 20)" },
        employee: {
          type: "string",
          description:
            "Filter by employee ID or name (e.g. 'HR-EMP-00001' or 'John Doe')",
        },
        status: {
          type: "string",
          description: "Filter by status (Draft, Submitted, Cancelled)",
          enum: ["Draft", "Submitted", "Cancelled"],
        },
        approval_status: {
          type: "string",
          description:
            "Filter by approval status (Pending, Approved, Rejected)",
          enum: ["Pending", "Approved", "Rejected"],
        },
        date_from: {
          type: "string",
          description: "Start date filter YYYY-MM-DD",
        },
        date_to: { type: "string", description: "End date filter YYYY-MM-DD" },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 20;
      const filters: FrappeFilter[] = [];
      if (input.employee) {
        filters.push([
          "employee",
          "=",
          await resolveEmployee(ctx.client, input.employee as string, {
            inputPath: "employee",
          }),
        ]);
      }
      if (input.status) {
        filters.push(["status", "=", input.status as string]);
      }
      if (input.approval_status) {
        filters.push(["approval_status", "=", input.approval_status as string]);
      }
      if (input.date_from) {
        filters.push(["posting_date", ">=", input.date_from as string]);
      }
      if (input.date_to) {
        filters.push(["posting_date", "<=", input.date_to as string]);
      }

      const docs = await ctx.client.list("Expense Claim", {
        fields: [
          "name",
          "employee",
          "employee_name",
          "posting_date",
          "total_claimed_amount",
          "status",
          "approval_status",
        ],
        filters,
        limit,
        order_by: "modified desc",
      });

      return {
        doctype: "Expense Claim",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  {
    name: "erpnext_expense_claim_create",
    description:
      "Create an Expense Claim using HRMS accounting rules. When settling an Employee Advance, the tool reads the official Advance Payment Ledger Entry rows and preserves the real Payment Entry references. It never accepts synthetic advance rows.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        employee: {
          type: "string",
          description:
            "Employee name or ID (e.g. HR-EMP-00001) — exact resolution on writes",
        },
        expenses: {
          type: "array",
          description: "List of expense line items",
          items: {
            type: "object",
            properties: {
              expense_type: {
                type: "string",
                description: "Expense Claim Type",
              },
              amount: { type: "number", description: "Claimed amount" },
              description: {
                type: "string",
                description: "Description of the expense (optional)",
              },
            },
            required: ["expense_type", "amount"],
          },
        },
        posting_date: {
          type: "string",
          description: "Posting date YYYY-MM-DD (optional)",
        },
        advances: {
          type: "array",
          description:
            "Employee Advance settlement requests. The tool resolves the real paid advance ledger rows automatically; do not supply reference_type/reference_name/advance_account manually.",
          items: {
            type: "object",
            properties: {
              employee_advance: {
                type: "string",
                description: "Employee Advance ID",
              },
              allocated_amount: {
                type: "number",
                description: "Amount to allocate from this advance",
              },
            },
            required: ["employee_advance", "allocated_amount"],
          },
        },
      },
      required: ["employee", "expenses"],
    },
    handler: async (input, ctx) => {
      if (!input.employee) {
        throw new Error(
          "[erpnext_expense_claim_create] 'employee' is required",
        );
      }

      if (
        !input.expenses ||
        !Array.isArray(input.expenses) ||
        (input.expenses as unknown[]).length === 0
      ) {
        throw new Error(
          "[erpnext_expense_claim_create] 'expenses' must be a non-empty array",
        );
      }

      const expenses = input.expenses as Array<{
        expense_type: string;
        amount: number;
        description?: string;
      }>;

      for (const e of expenses) {
        if (!e.expense_type) {
          throw new Error(
            "[erpnext_expense_claim_create] Every expense requires expense_type",
          );
        }
        if (
          typeof e.amount !== "number" ||
          !Number.isFinite(e.amount) ||
          e.amount <= 0
        ) {
          throw new Error(
            "[erpnext_expense_claim_create] Every expense amount must be greater than zero",
          );
        }
      }

      const employee = await resolveLink(
        ctx.client,
        "Employee",
        input.employee as string,
        "employee_name",
        { allowPartialMatch: false, inputPath: "employee" },
      );

      const employeeDoc = await ctx.client.get("Employee", employee, {
        skipCache: true,
      });
      const company = employeeDoc.company as string;

      if (!company) {
        throw new Error(
          `[erpnext_expense_claim_create] Employee ${employee} has no company`,
        );
      }

      const expenseLines = [];

      for (const e of expenses) {
        const expenseType = await ctx.client.get(
          "Expense Claim Type",
          e.expense_type,
          { skipCache: true },
        );

        const accountRows = (expenseType.accounts ?? []) as Array<{
          company?: string;
          default_account?: string;
        }>;

        const mapping = accountRows.find(
          (row) => row.company === company,
        );

        if (!mapping?.default_account) {
          throw new Error(
            `[erpnext_expense_claim_create] No default account configured for Expense Claim Type "${e.expense_type}" and company "${company}"`,
          );
        }

        expenseLines.push({
          expense_type: e.expense_type,
          amount: e.amount,
          description: e.description ?? "",
          default_account: mapping.default_account,
        });
      }

      const data: Record<string, unknown> = {
        employee,
        company,
        expenses: expenseLines,
      };

      if (input.posting_date) {
        data.posting_date = input.posting_date as string;
      }

      /*
       * IMPORTANT:
       * Never construct Expense Claim.advances manually.
       *
       * HRMS v16 builds these rows from Advance Payment Ledger Entry records.
       * This gives us the real Payment Entry reference, advance account,
       * payment date, paid amount, currency and current unclaimed amount.
       */
      if (input.advances) {
        if (
          !Array.isArray(input.advances) ||
          (input.advances as unknown[]).length === 0
        ) {
          throw new Error(
            "[erpnext_expense_claim_create] advances must be a non-empty array when supplied",
          );
        }

        const requestedAdvances = input.advances as Array<{
          employee_advance: string;
          allocated_amount: number;
        }>;

        const generatedRows: Array<Record<string, unknown>> = [];

        for (const request of requestedAdvances) {
          if (!request.employee_advance) {
            throw new Error(
              "[erpnext_expense_claim_create] employee_advance is required",
            );
          }

          if (
            typeof request.allocated_amount !== "number" ||
            !Number.isFinite(request.allocated_amount) ||
            request.allocated_amount <= 0
          ) {
            throw new Error(
              `[erpnext_expense_claim_create] Invalid allocation for ${request.employee_advance}`,
            );
          }

          const advance = await ctx.client.get(
            "Employee Advance",
            request.employee_advance,
            { skipCache: true },
          );

          if (advance.docstatus !== 1) {
            throw new Error(
              `Employee Advance ${request.employee_advance} is not submitted.`,
            );
          }

          if (advance.employee !== employee) {
            throw new Error(
              `Employee mismatch: Expense Claim employee ${employee} does not match Employee Advance ${request.employee_advance} (${advance.employee}).`,
            );
          }

          if (advance.company !== company) {
            throw new Error(
              `Company mismatch: Employee Advance ${request.employee_advance} belongs to "${advance.company}", while employee ${employee} belongs to "${company}".`,
            );
          }

          /*
           * Ask HRMS itself to build the complete Expense Claim advance
           * rows. This is the authoritative v16 path and includes the
           * actual Payment Entry reference(s).
           */
          const hrmsResult = await ctx.client.callMethod(
            "hrms.hr.doctype.expense_claim.expense_claim.get_expense_claim",
            {
              employee_advance: request.employee_advance,
            },
          );

          const candidate =
            (hrmsResult as any)?.message ??
            (hrmsResult as any)?.data ??
            hrmsResult;

          const hrmsAdvances = Array.isArray(candidate)
            ? candidate
            : Array.isArray(candidate?.advances)
              ? candidate.advances
              : Array.isArray(candidate?.message?.advances)
                ? candidate.message.advances
                : [];

          if (hrmsAdvances.length === 0) {
            throw new Error(
              `HRMS found no paid Advance Payment Ledger Entry for Employee Advance ${request.employee_advance}. The claim was not created.`,
            );
          }

          /*
           * Keep only rows belonging to this exact Employee Advance.
           * HRMS can return multiple rows when the advance was paid by
           * multiple Payment Entries.
           */
          const rows = hrmsAdvances.filter(
            (row: any) =>
              row.employee_advance === request.employee_advance,
          );

          if (rows.length === 0) {
            throw new Error(
              `HRMS returned advance rows, but none belongs to ${request.employee_advance}. The claim was not created.`,
            );
          }

          let remaining = request.allocated_amount;

          for (const row of rows) {
            if (remaining <= 0) break;

            const advanceAmount = Number(
              row.advance_amount ?? row.paid_amount ?? 0,
            );
            const claimedAmount = Number(row.claimed_amount ?? 0);
            const returnAmount = Number(row.return_amount ?? 0);
            const available = Math.max(
              advanceAmount - claimedAmount - returnAmount,
              0,
            );

            if (available <= 0) continue;

            const allocation = Math.min(remaining, available);

            if (!row.reference_type || !row.reference_name) {
              throw new Error(
                `HRMS returned an advance row without its real payment reference for ${request.employee_advance}. The claim was not created.`,
              );
            }

            if (!row.advance_account) {
              throw new Error(
                `HRMS returned an advance row without advance_account for ${request.employee_advance}. The claim was not created.`,
              );
            }

            generatedRows.push({
              reference_type: row.reference_type,
              reference_name: row.reference_name,
              advance_amount: Number(row.advance_amount ?? row.paid_amount ?? 0),
              allocated_amount: allocation,
              advance_account: row.advance_account,
              exchange_rate: Number(row.exchange_rate ?? 1),
              posting_date: row.posting_date,
              employee_advance: request.employee_advance,
            });

            remaining -= allocation;
          }

          if (remaining > 0.000001) {
            throw new Error(
              `Requested allocation ${request.allocated_amount} for ${request.employee_advance} exceeds the amount currently available according to HRMS (${request.allocated_amount - remaining}).`,
            );
          }
        }

        data.advances = generatedRows;
      }

      const doc = await ctx.client.create("Expense Claim", data);

      /*
       * Fresh read immediately after creation. The returned document is
       * the source of truth, not the create response alone.
       */
      const verified = await ctx.client.get(
        "Expense Claim",
        doc.name as string,
        { skipCache: true },
      );

      if (verified.employee !== employee) {
        throw new Error(
          `Post-create verification failed: Expense Claim ${doc.name} belongs to ${verified.employee}, expected ${employee}.`,
        );
      }

      if (verified.company !== company) {
        throw new Error(
          `Post-create verification failed: Expense Claim ${doc.name} belongs to ${verified.company}, expected ${company}.`,
        );
      }

      if (input.advances) {
        const verifiedAdvances = Array.isArray(verified.advances)
          ? verified.advances
          : [];

        if (verifiedAdvances.length === 0) {
          throw new Error(
            `Post-create verification failed: Expense Claim ${doc.name} has no advance rows.`,
          );
        }

        for (const row of verifiedAdvances) {
          if (!row.employee_advance) {
            throw new Error(
              `Post-create verification failed: Expense Claim ${doc.name} contains an advance row without employee_advance.`,
            );
          }
          if (!row.reference_type || !row.reference_name) {
            throw new Error(
              `Post-create verification failed: Expense Claim ${doc.name} contains an advance row without the real payment reference.`,
            );
          }
          if (!row.advance_account) {
            throw new Error(
              `Post-create verification failed: Expense Claim ${doc.name} contains an advance row without advance_account.`,
            );
          }
          if (!(Number(row.allocated_amount) > 0)) {
            throw new Error(
              `Post-create verification failed: Expense Claim ${doc.name} contains an advance row with zero allocation.`,
            );
          }
        }
      }

      return {
        data: verified,
        message: `Expense Claim ${doc.name} created and verified successfully`,
      };
    },
  },

  // ── Leave Balance ─────────────────────────────────────────────────────────

  {
    name: "erpnext_leave_balance",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description: "Get leave balance (allocations) for an employee. " +
      "Returns Leave Allocations with leave_type, total_leaves_allocated, new_leaves_allocated.",
    category: "hr",
    inputSchema: {
      type: "object",
      properties: {
        employee: {
          type: "string",
          description:
            "Employee ID or name (e.g. 'HR-EMP-00001' or 'John Doe')",
        },
      },
      required: ["employee"],
    },
    handler: async (input, ctx) => {
      if (!input.employee) {
        throw new Error("[erpnext_leave_balance] 'employee' is required");
      }

      const filters: FrappeFilter[] = [
        [
          "employee",
          "=",
          await resolveEmployee(ctx.client, input.employee as string, {
            inputPath: "employee",
          }),
        ],
        ["docstatus", "=", 1],
      ];

      const docs = await ctx.client.list("Leave Allocation", {
        fields: [
          "name",
          "leave_type",
          "total_leaves_allocated",
          "new_leaves_allocated",
          "from_date",
          "to_date",
        ],
        filters,
        limit: 50,
        order_by: "leave_type asc",
      });

      return {
        doctype: "Leave Allocation",
        employee: input.employee as string,
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },
];
