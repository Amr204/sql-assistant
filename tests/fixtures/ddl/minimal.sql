-- Minimal SSMS-style DDL fixture for parser unit tests.
-- Mirrors the structural patterns we expect from "Script Database As"
-- (bracketed identifiers, GO batches, PK/FK as separate constraints,
-- per-column defaults via ALTER TABLE, table name with a space).

USE [TestDB]
GO
/****** Object:  Table [dbo].[Customers] ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Customers](
	[CustomerID] [nchar](5) NOT NULL,
	[CompanyName] [nvarchar](40) NOT NULL,
	[ContactName] [nvarchar](30) NULL,
 CONSTRAINT [PK_Customers] PRIMARY KEY CLUSTERED 
(
	[CustomerID] ASC
)WITH (PAD_INDEX = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[Orders] ******/
SET ANSI_NULLS ON
GO
CREATE TABLE [dbo].[Orders](
	[OrderID] [int] IDENTITY(1,1) NOT NULL,
	[CustomerID] [nchar](5) NULL,
	[OrderDate] [datetime] NULL,
	[Freight] [money] NULL,
 CONSTRAINT [PK_Orders] PRIMARY KEY CLUSTERED 
(
	[OrderID] ASC
)WITH (PAD_INDEX = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  Table [dbo].[Order Details] ******/
SET ANSI_NULLS ON
GO
CREATE TABLE [dbo].[Order Details](
	[OrderID] [int] NOT NULL,
	[ProductID] [int] NOT NULL,
	[UnitPrice] [money] NOT NULL,
	[Quantity] [smallint] NOT NULL,
 CONSTRAINT [PK_Order_Details] PRIMARY KEY CLUSTERED 
(
	[OrderID] ASC,
	[ProductID] ASC
)WITH (PAD_INDEX = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
/****** Object:  View [dbo].[Active Customers] ******/
SET ANSI_NULLS ON
GO
create view [dbo].[Active Customers] AS
SELECT CustomerID, CompanyName
FROM Customers
WHERE ContactName IS NOT NULL
GO
/****** Object:  StoredProcedure [dbo].[GetCustomerOrders] ******/
CREATE PROCEDURE [dbo].[GetCustomerOrders] @CustomerID nchar(5)
AS
SELECT OrderID, OrderDate
FROM Orders
WHERE CustomerID = @CustomerID
GO
/****** Index ******/
CREATE NONCLUSTERED INDEX [IX_Orders_CustomerID] ON [dbo].[Orders]
(
	[CustomerID] ASC
)WITH (PAD_INDEX = OFF) ON [PRIMARY]
GO
CREATE UNIQUE NONCLUSTERED INDEX [UX_Customers_CompanyName] ON [dbo].[Customers]
(
	[CompanyName] ASC
)WITH (PAD_INDEX = OFF) ON [PRIMARY]
GO
/****** Defaults ******/
ALTER TABLE [dbo].[Orders] ADD  CONSTRAINT [DF_Orders_Freight]  DEFAULT ((0)) FOR [Freight]
GO
ALTER TABLE [dbo].[Order Details] ADD  CONSTRAINT [DF_Order_Details_Quantity]  DEFAULT ((1)) FOR [Quantity]
GO
/****** Foreign keys ******/
ALTER TABLE [dbo].[Orders]  WITH NOCHECK ADD  CONSTRAINT [FK_Orders_Customers] FOREIGN KEY([CustomerID])
REFERENCES [dbo].[Customers] ([CustomerID])
GO
ALTER TABLE [dbo].[Order Details]  WITH NOCHECK ADD  CONSTRAINT [FK_Order_Details_Orders] FOREIGN KEY([OrderID])
REFERENCES [dbo].[Orders] ([OrderID])
GO
