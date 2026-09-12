import os
import sys
import json
import tempfile
import subprocess
from agy_tools.adapters.nestjs_adapter import NestJSAdapter
from agy_tools.adapters.express_adapter import ExpressAdapter
from agy_tools.adapters.go_adapter import GoAdapter
from agy_tools.adapters.laravel_adapter import LaravelAdapter
from agy_tools.modules.doc_tool import (
    load_api_ignore,
    is_endpoint_ignored,
    compute_project_hash,
    export_markdown_modular,
    export_typescript_modular,
    export_postman_collection,
    group_endpoints_by_module
)

def test_nestjs_adapter_advanced():
    print("[TEST] Testing NestJS Adapter (DTOs, Prisma & Validation)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump({"dependencies": {"@nestjs/core": "^10.0.0", "@nestjs/common": "^10.0.0"}}, f)

        os.makedirs(os.path.join(tmpdir, "prisma"), exist_ok=True)
        with open(os.path.join(tmpdir, "prisma", "schema.prisma"), "w") as f:
            f.write("""
datasource db { provider = "postgresql" url = env("DATABASE_URL") }
model Product {
  id          String   @id @default(uuid())
  title       String
  price       Float
  isAvailable Boolean  @default(true)
  createdAt   DateTime @default(now())
}
""")

        os.makedirs(os.path.join(tmpdir, "src", "dto"), exist_ok=True)
        with open(os.path.join(tmpdir, "src", "dto", "create-product.dto.ts"), "w") as f:
            f.write("""
import { IsString, IsNumber, IsOptional, Min, IsEmail } from 'class-validator';

export class CreateProductDto {
  @IsString()
  title: string;

  @IsNumber()
  @Min(0)
  price: number;

  @IsOptional()
  @IsString()
  description?: string;
}
""")

        os.makedirs(os.path.join(tmpdir, "src", "controllers"), exist_ok=True)
        with open(os.path.join(tmpdir, "src", "controllers", "product.controller.ts"), "w") as f:
            f.write("""
import { Controller, Get, Post, Body, Param, UseGuards } from '@nestjs/common';
import { CreateProductDto } from '../dto/create-product.dto';

@Controller('api/v1/products')
@UseGuards(JwtAuthGuard)
export class ProductController {
  @Get()
  async listProducts() { return []; }

  @Post('create')
  async createProduct(@Body() dto: CreateProductDto) {
    return dto;
  }

  @Get(':id')
  async getProduct(@Param('id') id: string) {
    return { id };
  }
}
""")

        adapter = NestJSAdapter(tmpdir)
        assert adapter.detect() is True

        endpoints = adapter.scan()
        assert len(endpoints) == 3

        post_ep = next(e for e in endpoints if e["method"] == "POST")
        assert post_ep["path"] == "/api/v1/products/create"
        assert post_ep["handler"] == "createProduct"
        assert post_ep["auth"] is True
        assert post_ep["request_body"]["name"] == "CreateProductDto"
        props = post_ep["request_body"]["properties"]
        assert "title" in props and props["title"]["type"] == "string"
        assert "price" in props and props["price"]["type"] == "number" and props["price"]["min"] == 0
        assert "description" in props and props["description"]["required"] is False
    print("  ✓ NestJS Adapter tests passed.")

def test_express_zod_adapter():
    print("[TEST] Testing Express / Next.js Adapter with Zod schemas...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump({"dependencies": {"express": "^4.18.0", "zod": "^3.22.0"}}, f)

        with open(os.path.join(tmpdir, "routes.ts"), "w") as f:
            f.write("""
import { Router } from 'express';
import { z } from 'zod';

const router = Router();

export const UserRegisterSchema = z.object({
  username: z.string().min(3),
  email: z.string().email(),
  age: z.number().optional()
});

router.post('/api/users/register', (req, res) => {
  const data = UserRegisterSchema.parse(req.body);
  res.json({ success: true, data });
});

router.get('/api/users/:id', (req, res) => {
  res.json({ id: req.params.id });
});
""")

        adapter = ExpressAdapter(tmpdir)
        assert adapter.detect() is True

        endpoints = adapter.scan()
        assert len(endpoints) >= 2

        post_ep = next(e for e in endpoints if e["method"] == "POST")
        assert post_ep["path"] == "/api/users/register"
        assert post_ep["request_body"]["name"] == "UserRegisterSchema"
        assert post_ep["request_body"]["properties"]["email"]["format"] == "email"
        assert post_ep["request_body"]["properties"]["username"]["min"] == 3
    print("  ✓ Express / Zod Adapter tests passed.")

def test_go_adapter():
    print("[TEST] Testing Go Gin/Fiber Adapter & Struct tags...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "go.mod"), "w") as f:
            f.write("module testapp\n\ngo 1.22\n")

        with open(os.path.join(tmpdir, "main.go"), "w") as f:
            f.write("""
package main

import "github.com/gin-gonic/gin"

type CreateOrderReq struct {
	ItemName string  `json:"item_name" binding:"required"`
	Price    float64 `json:"price" binding:"required"`
	Quantity int     `json:"quantity,omitempty"`
}

func CreateOrder(c *gin.Context) {
	var req CreateOrderReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}
	c.JSON(200, gin.H{"status": "ok"})
}

func main() {
	r := gin.Default()
	r.POST("/api/orders", CreateOrder)
	r.GET("/api/orders/:id", GetOrder)
}
""")

        adapter = GoAdapter(tmpdir)
        assert adapter.detect() is True

        endpoints = adapter.scan()
        assert len(endpoints) == 2

        post_ep = next(e for e in endpoints if e["method"] == "POST")
        assert post_ep["path"] == "/api/orders"
        assert post_ep["request_body"]["name"] == "CreateOrderReq"
        assert post_ep["request_body"]["properties"]["item_name"]["required"] is True
        assert post_ep["request_body"]["properties"]["price"]["type"] == "number"
    print("  ✓ Go Adapter tests passed.")

def test_laravel_adapter():
    print("[TEST] Testing Laravel api.php & FormRequest Adapter...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "artisan"), "w") as f:
            f.write("#!/usr/bin/env php\n")

        os.makedirs(os.path.join(tmpdir, "routes"), exist_ok=True)
        with open(os.path.join(tmpdir, "routes", "api.php"), "w") as f:
            f.write(r"""<?php
use Illuminate\Support\Facades\Route;
use App\Http\Controllers\ArticleController;

Route::get('/articles', [ArticleController::class, 'index']);
Route::post('/articles', [ArticleController::class, 'store']);
Route::apiResource('comments', CommentController::class);
""")

        os.makedirs(os.path.join(tmpdir, "app", "Http", "Requests"), exist_ok=True)
        with open(os.path.join(tmpdir, "app", "Http", "Requests", "StoreArticleRequest.php"), "w") as f:
            f.write(r"""<?php
namespace App\Http\Requests;
use Illuminate\Foundation\Http\FormRequest;

class StoreArticleRequest extends FormRequest {
    public function rules(): array {
        return [
            'title' => 'required|string|max:255',
            'content' => ['required', 'string'],
            'views' => 'nullable|integer'
        ];
    }
}
""")

        adapter = LaravelAdapter(tmpdir)
        assert adapter.detect() is True

        endpoints = adapter.scan()
        assert len(endpoints) == 7

        store_ep = next(e for e in endpoints if e["method"] == "POST" and e["path"] == "/api/articles")
        assert store_ep["request_body"]["name"] == "StoreArticleRequest"
        assert store_ep["request_body"]["properties"]["title"]["required"] is True
        assert store_ep["request_body"]["properties"]["views"]["type"] == "number"
    print("  ✓ Laravel Adapter tests passed.")

def test_api_ignore_and_cache():
    print("[TEST] Testing .apiignore and incremental caching...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, ".apiignore"), "w") as f:
            f.write("""
# Ignore webhooks and billing
/api/webhooks/*
POST /api/payme/*
click
""")

        patterns = load_api_ignore(tmpdir)
        assert len(patterns) == 3

        ep_webhook = {"method": "POST", "path": "/api/webhooks/github", "handler": "handleHook"}
        ep_payme = {"method": "POST", "path": "/api/payme/checkout", "handler": "checkout"}
        ep_click = {"method": "GET", "path": "/api/click-callback", "handler": "callback"}
        ep_safe = {"method": "GET", "path": "/api/users", "handler": "listUsers"}

        assert is_endpoint_ignored(ep_webhook, patterns) is True
        assert is_endpoint_ignored(ep_payme, patterns) is True
        assert is_endpoint_ignored(ep_click, patterns) is True
        assert is_endpoint_ignored(ep_safe, patterns) is False

        h1 = compute_project_hash(tmpdir)
        with open(os.path.join(tmpdir, "test.ts"), "w") as f:
            f.write("console.log('updated');")
        h2 = compute_project_hash(tmpdir)
        assert h1 != h2
    print("  ✓ .apiignore and caching tests passed.")

def test_modular_exporters():
    print("[TEST] Testing Modular Exporters (docs/<module>/, types/<module>/, docs/README.md)...")
    sample_endpoints = [
        {
            "method": "POST",
            "path": "/api/v1/orders",
            "handler": "createOrder",
            "module": "orders",
            "summary": "Create a new order",
            "auth": True,
            "params": [],
            "query": [],
            "request_body": {
                "name": "CreateOrderRequest",
                "properties": {
                    "itemId": {"type": "string", "required": True},
                    "count": {"type": "number", "required": True, "min": 1}
                }
            },
            "response": {
                "status": 201,
                "type": "object",
                "properties": {
                    "orderId": {"type": "string", "required": True},
                    "status": {"type": "string", "required": True}
                }
            },
            "mock_request": {"itemId": "item_123", "count": 2},
            "mock_response": {"orderId": "ord_999", "status": "pending"},
            "file": "src/modules/orders/order.controller.ts",
            "line": 10
        },
        {
            "method": "GET",
            "path": "/api/v1/users",
            "handler": "listUsers",
            "module": "users",
            "summary": "List users",
            "auth": False,
            "params": [],
            "query": [],
            "request_body": None,
            "response": {
                "status": 200,
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "required": True},
                    "data": {"type": "array", "required": True}
                }
            },
            "mock_request": {},
            "mock_response": {"success": True, "data": []},
            "file": "src/modules/users/users.controller.ts",
            "line": 8
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        md_files = export_markdown_modular(sample_endpoints, tmpdir, "ModularProject")
        ts_files = export_typescript_modular(sample_endpoints, tmpdir)
        pm_file = os.path.join(tmpdir, "postman", "api_collection.json")
        export_postman_collection(sample_endpoints, pm_file, "ModularProject")

        orders_md = os.path.join(tmpdir, "docs", "orders", "api_contracts.md")
        users_md = os.path.join(tmpdir, "docs", "users", "api_contracts.md")
        readme_md = os.path.join(tmpdir, "docs", "README.md")
        master_md = os.path.join(tmpdir, "docs", "api_contracts.md")

        assert os.path.exists(orders_md), "orders/api_contracts.md should exist"
        assert os.path.exists(users_md), "users/api_contracts.md should exist"
        assert os.path.exists(readme_md), "docs/README.md should exist"
        assert os.path.exists(master_md), "docs/api_contracts.md should exist"

        with open(readme_md, "r") as f:
            readme_text = f.read()
            assert "Modullar Katalogi" in readme_text
            assert "[📂 `orders/api_contracts.md`](./orders/api_contracts.md)" in readme_text
            assert "[📂 `users/api_contracts.md`](./users/api_contracts.md)" in readme_text

        with open(orders_md, "r") as f:
            orders_text = f.read()
            assert "Orders Moduli" in orders_text
            assert "CreateOrderRequest" in orders_text

        orders_ts = os.path.join(tmpdir, "types", "orders", "api.contracts.d.ts")
        users_ts = os.path.join(tmpdir, "types", "users", "api.contracts.d.ts")
        master_ts = os.path.join(tmpdir, "types", "api.contracts.d.ts")
        index_ts = os.path.join(tmpdir, "types", "index.d.ts")

        assert os.path.exists(orders_ts)
        assert os.path.exists(users_ts)
        assert os.path.exists(master_ts)
        assert os.path.exists(index_ts)

        with open(orders_ts, "r") as f:
            orders_ts_text = f.read()
            assert "export namespace OrdersContracts" in orders_ts_text
            assert "export interface CreateOrderRequest" in orders_ts_text

        with open(master_ts, "r") as f:
            master_ts_text = f.read()
            assert "export namespace ApiContracts" in master_ts_text
            assert "export interface CreateOrderRequest" in master_ts_text

        assert os.path.exists(pm_file)
        with open(pm_file, "r") as f:
            pm_data = json.load(f)
            folder_names = [f["name"] for f in pm_data["item"]]
            assert "📦 Orders" in folder_names
            assert "📦 Users" in folder_names

    print("  ✓ Modular Exporters tests passed.")

def test_nestjs_dto_multiline_and_exclamation():
    print("[TEST] Testing NestJS Adapter Multiline Decorators & Exclamation Mark fields (BUG-002)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump({"dependencies": {"@nestjs/core": "^10.0.0", "@nestjs/common": "^10.0.0"}}, f)

        os.makedirs(os.path.join(tmpdir, "src", "modules", "company", "dto"), exist_ok=True)
        with open(os.path.join(tmpdir, "src", "modules", "company", "dto", "create-company.dto.ts"), "w") as f:
            f.write("""
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import {
  IsEmail,
  IsOptional,
  IsString,
  IsTimeZone,
  MaxLength,
  MinLength,
} from 'class-validator';

export class CreateCompanyDto {
  @ApiProperty({
    example: 'ZDES',
  })
  @IsString()
  @MinLength(1)
  @MaxLength(255)
  name!: string;

  @ApiPropertyOptional({
    example: 'ZDES LLC',
  })
  @IsOptional()
  @IsString()
  @MaxLength(255)
  legalName?: string;

  @ApiPropertyOptional({
    example: '+998901234567',
  })
  @IsOptional()
  @IsString()
  @MaxLength(50)
  phone?: string;

  @ApiPropertyOptional({
    example: 'info@zdes.uz',
  })
  @IsOptional()
  @IsEmail()
  @MaxLength(255)
  email?: string;

  @ApiPropertyOptional({
    example: 'Tashkent city, Yunusobod district',
  })
  @IsOptional()
  @IsString()
  @MaxLength(500)
  address?: string;

  @ApiPropertyOptional({
    example: 'Asia/Tashkent',
    default: 'Asia/Tashkent',
    description:
      'IANA timezone used to compute attendance schedules for this company',
  })
  @IsOptional()
  @IsTimeZone()
  timezone?: string;
}
""")

        adapter = NestJSAdapter(tmpdir)
        adapter._parse_dto_files()

        assert "CreateCompanyDto" in adapter.dtos, "CreateCompanyDto should be parsed"
        props = adapter.dtos["CreateCompanyDto"]["properties"]

        # 1. Definite assignment assertion 'name!: string' should be captured and required
        assert "name" in props, "'name' field must be captured"
        assert props["name"]["type"] == "string"
        assert props["name"]["required"] is True
        assert props["name"]["minLength"] == 1
        assert props["name"]["maxLength"] == 255

        # 2. Optional properties
        assert "legalName" in props and props["legalName"]["required"] is False
        assert "phone" in props and props["phone"]["required"] is False
        assert "email" in props and props["email"]["format"] == "email" and props["email"]["required"] is False
        assert "address" in props and props["address"]["required"] is False
        assert "timezone" in props and props["timezone"]["required"] is False

        # 3. No fake fields from multiline decorator arguments
        assert "example" not in props, "Fake property 'example' should NOT exist"
        assert "default" not in props, "Fake property 'default' should NOT exist"
        assert "description" not in props, "Fake property 'description' should NOT exist"

        print("  ✓ NestJS DTO multiline decorators & exclamation mark tests passed (BUG-002 fixed).")

def main():
    test_nestjs_adapter_advanced()
    test_nestjs_dto_multiline_and_exclamation()
    test_express_zod_adapter()
    test_go_adapter()
    test_laravel_adapter()
    test_api_ignore_and_cache()
    test_modular_exporters()
    print("🎉 ALL DOC TOOL & ADAPTER TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
