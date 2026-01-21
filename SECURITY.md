# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | Yes                |

## Reporting a Vulnerability

If you discover a security vulnerability in Altimate Data Skills, please report it responsibly.

### How to Report

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Email the maintainers directly or use GitHub's private vulnerability reporting feature
3. Include as much detail as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes

### What to Expect

- We will acknowledge receipt within 48 hours
- We will provide an initial assessment within 7 days
- We will work with you to understand and resolve the issue
- We will credit you in the fix announcement (unless you prefer to remain anonymous)

## Security Considerations

Since these are Claude Code skills (markdown instruction files), the primary security considerations are:

- **Skill instructions**: Skills should not instruct Claude to perform dangerous operations
- **Command injection**: Skills should use safe patterns when suggesting shell commands
- **Sensitive data**: Skills should remind Claude not to expose sensitive information

## Best Practices for Skill Authors

When creating new skills:

1. Never include hardcoded credentials or secrets
2. Use parameterized commands rather than string interpolation
3. Include appropriate warnings for destructive operations
4. Follow the principle of least privilege in suggested commands
