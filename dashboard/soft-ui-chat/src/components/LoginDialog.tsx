/**
 * LoginDialog Component
 *
 * Full-screen authentication component for user login and registration.
 * Displays when user is not authenticated, with a tabbed interface
 * for switching between login and register forms.
 *
 * Features:
 * - Login form with email/password
 * - Register form with email, password, confirm password, first/last name
 * - Form validation with error messages
 * - Loading states during submission
 * - Toast notifications for errors
 * - Styled to match the soft-UI aesthetic
 */
import { useState, FormEvent } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/useAuth';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';

// ============================================
// Types
// ============================================

interface FormErrors {
  email?: string;
  password?: string;
  confirmPassword?: string;
  firstName?: string;
  lastName?: string;
}

// ============================================
// Component
// ============================================

export function LoginDialog() {
  // Auth hook
  const { login, register, isLoading } = useAuth();

  // Form state - Login
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginErrors, setLoginErrors] = useState<FormErrors>({});

  // Form state - Register
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [registerConfirmPassword, setRegisterConfirmPassword] = useState('');
  const [registerFirstName, setRegisterFirstName] = useState('');
  const [registerLastName, setRegisterLastName] = useState('');
  const [registerErrors, setRegisterErrors] = useState<FormErrors>({});

  // ============================================
  // Validation Functions
  // ============================================

  /**
   * Validate email format
   */
  function validateEmail(email: string): string | undefined {
    if (!email.trim()) {
      return 'Email is required';
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return 'Please enter a valid email address';
    }
    return undefined;
  }

  /**
   * Validate password strength
   */
  function validatePassword(password: string): string | undefined {
    if (!password) {
      return 'Password is required';
    }
    if (password.length < 8) {
      return 'Password must be at least 8 characters';
    }
    return undefined;
  }

  /**
   * Validate confirm password matches
   */
  function validateConfirmPassword(password: string, confirmPassword: string): string | undefined {
    if (!confirmPassword) {
      return 'Please confirm your password';
    }
    if (password !== confirmPassword) {
      return 'Passwords do not match';
    }
    return undefined;
  }

  /**
   * Validate login form
   */
  function validateLoginForm(): boolean {
    const errors: FormErrors = {};

    const emailError = validateEmail(loginEmail);
    if (emailError) errors.email = emailError;

    if (!loginPassword) {
      errors.password = 'Password is required';
    }

    setLoginErrors(errors);
    return Object.keys(errors).length === 0;
  }

  /**
   * Validate registration form
   */
  function validateRegisterForm(): boolean {
    const errors: FormErrors = {};

    const emailError = validateEmail(registerEmail);
    if (emailError) errors.email = emailError;

    const passwordError = validatePassword(registerPassword);
    if (passwordError) errors.password = passwordError;

    const confirmPasswordError = validateConfirmPassword(registerPassword, registerConfirmPassword);
    if (confirmPasswordError) errors.confirmPassword = confirmPasswordError;

    setRegisterErrors(errors);
    return Object.keys(errors).length === 0;
  }

  // ============================================
  // Form Handlers
  // ============================================

  /**
   * Handle login form submission
   */
  async function handleLogin(e: FormEvent) {
    e.preventDefault();

    if (!validateLoginForm()) {
      return;
    }

    try {
      await login(loginEmail, loginPassword);
      // Success - no need to show toast, user will be redirected
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Login failed. Please try again.';
      toast.error(message);
    }
  }

  /**
   * Handle registration form submission
   */
  async function handleRegister(e: FormEvent) {
    e.preventDefault();

    if (!validateRegisterForm()) {
      return;
    }

    try {
      await register(
        registerEmail,
        registerPassword,
        registerFirstName || undefined,
        registerLastName || undefined
      );
      // Success - no need to show toast, user will be redirected
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Registration failed. Please try again.';
      toast.error(message);
    }
  }

  // ============================================
  // Render
  // ============================================

  return (
    <div className="flex h-full w-full items-center justify-center bg-[#e0e5ec] p-6">
      <Card className="w-full max-w-md rounded-3xl border-border/50 shadow-lg">
        <CardHeader className="space-y-2 text-center">
          <CardTitle className="text-2xl font-semibold tracking-tight">TubeVibe</CardTitle>
          <CardDescription className="text-muted-foreground">
            Sign in to access your video library
          </CardDescription>
        </CardHeader>

        <CardContent>
          <Tabs defaultValue="login" className="w-full">
            <TabsList className="grid w-full grid-cols-2 rounded-xl bg-muted">
              <TabsTrigger
                value="login"
                className="rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm"
              >
                Login
              </TabsTrigger>
              <TabsTrigger
                value="register"
                className="rounded-lg data-[state=active]:bg-background data-[state=active]:shadow-sm"
              >
                Register
              </TabsTrigger>
            </TabsList>

            {/* Login Tab */}
            <TabsContent value="login" className="mt-6">
              <form onSubmit={handleLogin} className="space-y-4">
                {/* Email Field */}
                <div className="space-y-2">
                  <Label htmlFor="login-email">Email</Label>
                  <Input
                    id="login-email"
                    type="email"
                    placeholder="you@example.com"
                    value={loginEmail}
                    onChange={(e) => {
                      setLoginEmail(e.target.value);
                      if (loginErrors.email) {
                        setLoginErrors((prev) => ({ ...prev, email: undefined }));
                      }
                    }}
                    className={`rounded-xl ${loginErrors.email ? 'border-destructive' : ''}`}
                    disabled={isLoading}
                    autoComplete="email"
                  />
                  {loginErrors.email && (
                    <p className="text-sm text-destructive">{loginErrors.email}</p>
                  )}
                </div>

                {/* Password Field */}
                <div className="space-y-2">
                  <Label htmlFor="login-password">Password</Label>
                  <Input
                    id="login-password"
                    type="password"
                    placeholder="Enter your password"
                    value={loginPassword}
                    onChange={(e) => {
                      setLoginPassword(e.target.value);
                      if (loginErrors.password) {
                        setLoginErrors((prev) => ({ ...prev, password: undefined }));
                      }
                    }}
                    className={`rounded-xl ${loginErrors.password ? 'border-destructive' : ''}`}
                    disabled={isLoading}
                    autoComplete="current-password"
                  />
                  {loginErrors.password && (
                    <p className="text-sm text-destructive">{loginErrors.password}</p>
                  )}
                </div>

                {/* Submit Button */}
                <Button
                  type="submit"
                  className="w-full rounded-xl"
                  disabled={isLoading}
                >
                  {isLoading ? 'Signing in...' : 'Sign in'}
                </Button>
              </form>
            </TabsContent>

            {/* Register Tab */}
            <TabsContent value="register" className="mt-6">
              <form onSubmit={handleRegister} className="space-y-4">
                {/* Name Fields (Optional) */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="register-first-name">
                      First Name <span className="text-muted-foreground">(optional)</span>
                    </Label>
                    <Input
                      id="register-first-name"
                      type="text"
                      placeholder="John"
                      value={registerFirstName}
                      onChange={(e) => setRegisterFirstName(e.target.value)}
                      className="rounded-xl"
                      disabled={isLoading}
                      autoComplete="given-name"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="register-last-name">
                      Last Name <span className="text-muted-foreground">(optional)</span>
                    </Label>
                    <Input
                      id="register-last-name"
                      type="text"
                      placeholder="Doe"
                      value={registerLastName}
                      onChange={(e) => setRegisterLastName(e.target.value)}
                      className="rounded-xl"
                      disabled={isLoading}
                      autoComplete="family-name"
                    />
                  </div>
                </div>

                {/* Email Field */}
                <div className="space-y-2">
                  <Label htmlFor="register-email">Email</Label>
                  <Input
                    id="register-email"
                    type="email"
                    placeholder="you@example.com"
                    value={registerEmail}
                    onChange={(e) => {
                      setRegisterEmail(e.target.value);
                      if (registerErrors.email) {
                        setRegisterErrors((prev) => ({ ...prev, email: undefined }));
                      }
                    }}
                    className={`rounded-xl ${registerErrors.email ? 'border-destructive' : ''}`}
                    disabled={isLoading}
                    autoComplete="email"
                  />
                  {registerErrors.email && (
                    <p className="text-sm text-destructive">{registerErrors.email}</p>
                  )}
                </div>

                {/* Password Field */}
                <div className="space-y-2">
                  <Label htmlFor="register-password">Password</Label>
                  <Input
                    id="register-password"
                    type="password"
                    placeholder="At least 8 characters"
                    value={registerPassword}
                    onChange={(e) => {
                      setRegisterPassword(e.target.value);
                      if (registerErrors.password) {
                        setRegisterErrors((prev) => ({ ...prev, password: undefined }));
                      }
                    }}
                    className={`rounded-xl ${registerErrors.password ? 'border-destructive' : ''}`}
                    disabled={isLoading}
                    autoComplete="new-password"
                  />
                  {registerErrors.password && (
                    <p className="text-sm text-destructive">{registerErrors.password}</p>
                  )}
                </div>

                {/* Confirm Password Field */}
                <div className="space-y-2">
                  <Label htmlFor="register-confirm-password">Confirm Password</Label>
                  <Input
                    id="register-confirm-password"
                    type="password"
                    placeholder="Confirm your password"
                    value={registerConfirmPassword}
                    onChange={(e) => {
                      setRegisterConfirmPassword(e.target.value);
                      if (registerErrors.confirmPassword) {
                        setRegisterErrors((prev) => ({ ...prev, confirmPassword: undefined }));
                      }
                    }}
                    className={`rounded-xl ${registerErrors.confirmPassword ? 'border-destructive' : ''}`}
                    disabled={isLoading}
                    autoComplete="new-password"
                  />
                  {registerErrors.confirmPassword && (
                    <p className="text-sm text-destructive">{registerErrors.confirmPassword}</p>
                  )}
                </div>

                {/* Submit Button */}
                <Button
                  type="submit"
                  className="w-full rounded-xl"
                  disabled={isLoading}
                >
                  {isLoading ? 'Creating account...' : 'Create account'}
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}

export default LoginDialog;
