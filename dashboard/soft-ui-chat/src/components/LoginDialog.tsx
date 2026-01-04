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
  const { login, register, googleLogin, isLoading } = useAuth();

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

                {/* Divider */}
                <div className="relative my-4">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t border-border" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-card px-2 text-muted-foreground">Or continue with</span>
                  </div>
                </div>

                {/* Google Sign In Button */}
                <Button
                  type="button"
                  variant="outline"
                  className="w-full rounded-xl flex items-center justify-center gap-2"
                  onClick={googleLogin}
                  disabled={isLoading}
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24">
                    <path
                      fill="currentColor"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="currentColor"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="currentColor"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="currentColor"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                  Sign in with Google
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

                {/* Divider */}
                <div className="relative my-4">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t border-border" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-card px-2 text-muted-foreground">Or continue with</span>
                  </div>
                </div>

                {/* Google Sign In Button */}
                <Button
                  type="button"
                  variant="outline"
                  className="w-full rounded-xl flex items-center justify-center gap-2"
                  onClick={googleLogin}
                  disabled={isLoading}
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24">
                    <path
                      fill="currentColor"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="currentColor"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="currentColor"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="currentColor"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                  Sign up with Google
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
