-- Removed key in a template file rendered by an operator (template_ext).

DELETE FROM sales WHERE sale_date = '{{ yesterday_ds }}';
INSERT INTO sales SELECT * FROM staging WHERE sale_date = '{{ ds }}';
