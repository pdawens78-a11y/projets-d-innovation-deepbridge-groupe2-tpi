using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Printing;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using DeepBridgeWindowsApp.Dicom;
using OpenTK.GLControl;
using OpenTK.Graphics.OpenGL;
using OpenTK.Mathematics;
using System.IO;

namespace DeepBridgeWindowsApp
{
    public partial class RenderDicomForm : Form
    {
        //Min and Max values from the trackbars
        private int minSlice;
        private int maxSlice;

        // Composants principaux
        private Dicom3D render;
        private readonly DicomMetadata dicom;
        private readonly DicomDisplayManager ddm;
        private GLControl gl;
        private ProgressBar progressBar;
        private Label progressLabel;
        private Label controlsHelpLabel;
        private Label controlsLabel;
        private readonly string patientDirectory;

        // Propriétés de la caméra
        private Vector3 cameraPosition = new Vector3(0, 0, 3f);
        private Vector3 cameraTarget = Vector3.Zero;
        private Vector3 cameraUp = Vector3.UnitY;
        private float rotationX = 0;
        private float rotationY = 0;
        private float zoom = 3.0f;

        // Contrôles de la souris
        private Point lastMousePos;
        private bool isMouseDown = false;

        // Contrôles clavier
        private readonly float moveSpeed = 0.1f;
        private readonly HashSet<Keys> pressedKeys = new HashSet<Keys>();
        private System.Windows.Forms.Timer moveTimer;

        // Contrôles des couches
        private TrackBar frontClipTrackBar;
        private TrackBar backClipTrackBar;
        private Label frontClipLabel;
        private Label backClipLabel;

        // Slice Button
        private Button sliceButton;
        private PictureBox slicePreview;
        private NumericUpDown slicePositionX;
        private NumericUpDown slicePositionZ;
        private CheckBox checkBox;
        private NumericUpDown angleYZInput;
        private NumericUpDown angleXYInput;

        // Debug
        private Label debugLabel;

        // Slice indicator
        private int[] sliceIndicatorVBO;
        private readonly float[] sliceIndicatorVertices = {
            // Front face vertices
            0f, 0.5f, 0.5f,
            0f, -0.5f, 0.5f,
            0f, -0.5f, -0.5f,
            0f, 0.5f, -0.5f,
        };
        private int sliceWidth;
        private CancellationTokenSource _sliceUpdateCts;
        private readonly int _debounceMs = 150; // Adjust this value to control debounce timing
        private Task _currentSliceTask;
        private Rectangle? carotidRect;

        // Shaders
        private int shaderProgram;
        private int ColorShaderProgram;
        private const string vertexShaderSource = @"
        #version 330 core
        layout(location = 0) in vec3 aPosition;
        layout(location = 1) in vec3 aColor;
        out vec3 vertexColor;
        uniform mat4 model;
        uniform mat4 view;
        uniform mat4 projection;
        void main()
        {
            gl_Position = projection * view * model * vec4(aPosition, 1.0);
            vertexColor = aColor;
        }";

        private const string fragmentShaderSource = @"
        #version 330 core
        in vec3 vertexColor;
        out vec4 FragColor;
        void main()
        {
            FragColor = vec4(vertexColor, 1.0);
        }";

        private const string ColorVertexShader = @"#version 330 core
        layout(location = 0) in vec3 aPosition;
        uniform mat4 model;
        uniform mat4 view;
        uniform mat4 projection;
        void main() {
            gl_Position = projection * view * model * vec4(aPosition, 1.0);
        }";

        private const string ColorFragmentShader = @"#version 330 core
        uniform vec3 color;
        out vec4 FragColor;
        void main() {
            FragColor = vec4(color, 0.5);
        }";

        public RenderDicomForm(DicomDisplayManager ddm, int minSlice, int maxSlice, string patientDirectory, Rectangle? carotidRect = null)
        {
            this.ddm = ddm;
            this.minSlice = minSlice;
            this.maxSlice = maxSlice;
            this.dicom = this.ddm.globalView;
            this.sliceWidth = ddm.GetSlice(0).Columns;
            this.carotidRect = carotidRect;
            this.patientDirectory = patientDirectory;
            InitializeComponents();
            InitializeKeyboardControls();
        }

        private void InitializeComponents()
        {
            this.Size = new Size(1424, 768);
            this.Text = "DICOM Render";

            InitializeLeftPanel();
            InitializeGLControl();
            InitializeProgressBar();
            this.Controls.Add(gl);
        }

        private void InitializeLeftPanel()
        {
            var leftPanel = new Panel
            {
                Dock = DockStyle.Left,
                Width = 200,
                Padding = new Padding(5, 5, 5, 10),
                BackColor = Color.FromArgb(40, 40, 40)
            };

            // Créer un FlowLayoutPanel pour organiser les contrôles verticalement
            var flowPanel = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                FlowDirection = FlowDirection.TopDown,
                //AutoSize = true,
                Width = 200,
                WrapContents = false
            };

            // Label des contrôles
            controlsLabel = new Label
            {
                AutoSize = true,
                ForeColor = Color.White,
                Font = new Font(Font.FontFamily, 9),
                Text = "Contrôles:\n\n" +
                       "ZQSD/WASD :\nDéplacement\n\n" +
                       "E/C :\nMonter/Descendre\n\n" +
                       "Souris :\nRotation\n\n" +
                       "Molette :\nZoom\n\n" +
                       "R :\nRéinitialiser la vue\n\n"
            };

            // Panel pour les contrôles de découpage
            var clipPanel = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(40, 40, 40),
                Width = 200,
                //Margin = new Padding(5)
            };

            // Label pour le titre des trackbars
            var clipLabel = new Label
            {
                Text = "Contrôles de découpage:",
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(5, 5)
            };

            frontClipTrackBar = new TrackBar
            {
                Minimum = 0,
                Maximum = ddm.GetTotalSlices() - 1,
                Value = 0,
                Location = new Point(10, 25),
                Width = 180
            };
            frontClipTrackBar.ValueChanged += ClipTrackBar_ValueChanged;

            backClipTrackBar = new TrackBar
            {
                Minimum = 0,
                Maximum = ddm.GetTotalSlices() - 1,
                Value = 0,
                Location = new Point(10, 65),
                Width = 180
            };
            backClipTrackBar.ValueChanged += ClipTrackBar_ValueChanged;

            // Labels pour les trackbars
            frontClipLabel = new Label
            {
                Text = "Couches avant: 0",
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(10, 45)
            };

            backClipLabel = new Label
            {
                Text = "Couches arrière: 0",
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(10, 85)
            };

            // Ajouter les contrôles au FlowLayoutPanel
            checkBox = new CheckBox
            {
                Text = "Show Live Slice",
                ForeColor = Color.White,
                AutoSize = true,
                Checked = false
            };

            checkBox.CheckedChanged += (s, e) =>
            {
                gl.Invalidate();
                if (checkBox.Checked)
                {
                    // Créer et initialiser la preview seulement quand on active la checkbox
                    if (slicePreview == null)
                    {
                        InitializeSlicePreview();
                    }
                    UpdateSlicePreview();
                }
                else if (slicePreview != null)
                {
                    slicePreview.Visible = false;
                }
            };

            slicePositionX = new NumericUpDown
            {
                Minimum = 0,                  // First pixel row
                Maximum = sliceWidth - 1,     // Last pixel row
                Value = sliceWidth / 2,       // Start at middle
            };
            slicePositionX.ValueChanged += (s, e) => gl.Invalidate();

            // Label to show slice position
            var slicePositionXLabel = new Label
            {
                Text = "X Position",
                ForeColor = Color.White,
                AutoSize = true
            };

            var slicePositionZLabel = new Label
            {
                Text = "Z Position",
                ForeColor = Color.White,
                AutoSize = true
            };

            slicePositionZ = new NumericUpDown
            {
                Minimum = 0,
                Maximum = ddm.GetTotalSlices() - 1,
                Value = ddm.GetTotalSlices() / 2,
                Width = 80
            };
            slicePositionZ.ValueChanged += (s, e) => gl.Invalidate();

            // Add slice button
            //sliceButton = new Button
            //{
            //    Dock = DockStyle.Bottom,
            //    Text = "Extract Slice",
            //    AutoSize = true,
            //    ForeColor = Color.White
            //};
            //sliceButton.Click += SliceButton_Click;

            //clipPanel.Controls.AddRange(new Control[] {
            //    clipLabel,
            //    frontClipTrackBar,
            //    backClipTrackBar,
            //    frontClipLabel,
            //    backClipLabel,
            //});

            // YZ rotation (around X axis)
            var angleYZLabel = new Label
            {
                Text = "YZ Rotation (degrees)",
                ForeColor = Color.White,
                AutoSize = true
            };

            angleYZInput = new NumericUpDown
            {
                Minimum = -180,
                Maximum = 180,
                Value = 90,
                DecimalPlaces = 1,
                Increment = 1m
            };
            angleYZInput.ValueChanged += (s, e) => gl.Invalidate();

            // XY rotation (around Z axis)
            var angleXYLabel = new Label
            {
                Text = "XY Rotation (degrees)",
                ForeColor = Color.White,
                AutoSize = true
            };

            angleXYInput = new NumericUpDown  // Renamed from angleXZInput
            {
                Minimum = -180,
                Maximum = 180,
                Value = 0,
                DecimalPlaces = 1,
                Increment = 1m
            };
            angleXYInput.ValueChanged += (s, e) => gl.Invalidate();

            slicePositionX.ValueChanged += (s, e) => UpdateSlicePreview();
            slicePositionZ.ValueChanged += (s, e) => UpdateSlicePreview();
            angleYZInput.ValueChanged += (s, e) => UpdateSlicePreview();
            angleXYInput.ValueChanged += (s, e) => UpdateSlicePreview();

            this.Controls.Add(slicePreview);

            // Ajouter les contrôles au FlowLayoutPanel
            flowPanel.Controls.Add(controlsLabel);

            //flowPanel.Controls.Add(clipPanel);
            //flowPanel.Controls.Add(sliceButton);
            flowPanel.Controls.Add(checkBox);
            flowPanel.Controls.Add(slicePositionXLabel);
            flowPanel.Controls.Add(slicePositionX);
            flowPanel.Controls.Add(slicePositionZLabel);
            flowPanel.Controls.Add(slicePositionZ);

            flowPanel.Controls.Add(angleYZLabel);
            flowPanel.Controls.Add(angleYZInput);
            flowPanel.Controls.Add(angleXYLabel);
            flowPanel.Controls.Add(angleXYInput);

            // Ajouter le FlowLayoutPanel au panel gauche
            leftPanel.Controls.Add(flowPanel);
            leftPanel.Controls.Add(sliceButton);

            debugLabel = new Label
            {
                AutoSize = true,
                Anchor = AnchorStyles.Bottom | AnchorStyles.Right,
                ForeColor = Color.White,
                BackColor = Color.Black,
                Location = new Point(this.ClientSize.Width - 100, this.ClientSize.Height - 20) // Adjust the location to stick to the bottom right
            };
            this.Controls.Add(debugLabel);
            this.Resize += (s, e) =>
            {
                debugLabel.Location = new Point(this.ClientSize.Width - debugLabel.Width - 10, this.ClientSize.Height - debugLabel.Height - 10);
            };

            this.Controls.Add(leftPanel);
        }

        private void InitializeGLControl()
        {
            gl = new GLControl { Dock = DockStyle.Fill };
            gl.Resize += GLControl_Resize;
            gl.MouseDown += GL_MouseDown;
            gl.MouseUp += GL_MouseUp;
            gl.MouseMove += GL_MouseMove;
            gl.MouseWheel += GL_MouseWheel;
            gl.Focus();
        }

        private void InitializeProgressBar()
        {
            progressBar = new ProgressBar
            {
                Width = 300,
                Height = 23,
                Style = ProgressBarStyle.Continuous,
                Visible = false
            };

            progressLabel = new Label
            {
                AutoSize = true,
                Width = 300,
                TextAlign = ContentAlignment.MiddleCenter,
                Visible = false
            };

            progressBar.Location = new Point(
                (this.ClientSize.Width - progressBar.Width) / 2,
                (this.ClientSize.Height - progressBar.Height) / 2
            );
            progressLabel.Location = new Point(
                (this.ClientSize.Width - progressLabel.Width) / 2,
                progressBar.Location.Y - 25
            );

            this.Controls.Add(progressBar);
            this.Controls.Add(progressLabel);
        }

        private void InitializeKeyboardControls()
        {
            this.KeyPreview = true;
            this.KeyDown += RenderDicomForm_KeyDown;
            this.KeyUp += RenderDicomForm_KeyUp;
            this.Activated += (s, e) => gl?.Focus();

            moveTimer = new System.Windows.Forms.Timer
            {
                Interval = 16 // ~60 FPS
            };
            moveTimer.Tick += MoveTimer_Tick;
            moveTimer.Start();
        }


        private void ClipTrackBar_ValueChanged(object sender, EventArgs e)
        {
            // Vérifier que les valeurs sont valides
            if (frontClipTrackBar.Value + backClipTrackBar.Value >= ddm.GetTotalSlices())
            {
                if (sender == frontClipTrackBar)
                    frontClipTrackBar.Value = ddm.GetTotalSlices() - 1 - backClipTrackBar.Value;
                else
                    backClipTrackBar.Value = ddm.GetTotalSlices() - 1 - frontClipTrackBar.Value;
            }

            controlsLabel.Text = $"Contrôles:\n\n" +
                                 "ZQSD/WASD :\nDéplacement\n\n" +
                                 "E/C :\nMonter/Descendre\n\n" +
                                 "Souris :\nRotation\n\n" +
                                 "Molette :\nZoom\n\n" +
                                 "R :\nRéinitialiser la vue\n\n" +
                                 $"Couches avant: {frontClipTrackBar.Value}\n" +
                                 $"Couches arrière: {backClipTrackBar.Value}";

            render.SetClipPlanes(frontClipTrackBar.Value, backClipTrackBar.Value);
            gl.Invalidate();
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            this.Shown += RenderDicomForm_Load;
        }

        private Bitmap RotateImage(Bitmap original)
        {
            var rotated = new Bitmap(original.Height, original.Width);
            using (Graphics g = Graphics.FromImage(rotated))
            {
                g.TranslateTransform(0, original.Width);
                g.RotateTransform(-90);
                g.DrawImage(original, 0, 0);
            }
            return rotated;
        }

        private void SaveSlice(Bitmap slice)
        {
            using (SaveFileDialog saveDialog = new SaveFileDialog())
            {
                saveDialog.Filter = "PNG Image|*.png|JPEG Image|*.jpg|Bitmap Image|*.bmp";
                saveDialog.Title = "Save Slice Image";
                saveDialog.DefaultExt = "png";

                if (saveDialog.ShowDialog() == DialogResult.OK)
                {
                    try
                    {
                        slice.Save(saveDialog.FileName);
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show($"Error saving slice: {ex.Message}");
                    }
                }
            }
        }

        private async void UpdateSlicePreview()
        {
            if (!checkBox.Checked) return;

            if (_sliceUpdateCts != null)
            {
                _sliceUpdateCts.Cancel();
                _sliceUpdateCts.Dispose();
            }
            _sliceUpdateCts = new CancellationTokenSource();
            var token = _sliceUpdateCts.Token;

            try
            {
                // Wait for debounce period
                await Task.Delay(_debounceMs, token);

                if (render == null) return;

                float normalizedX = ((float)slicePositionX.Value / (sliceWidth - 1)) - 0.5f;
                float normalizedZ = ((float)slicePositionZ.Value / (ddm.GetTotalSlices() - 1)) - 0.5f;
                float angleYZ = (float)((double)angleYZInput.Value * Math.PI / 180.0);
                float angleXY = (float)((double)angleXYInput.Value * Math.PI / 180.0);

                _currentSliceTask = Task.Run(async () =>
                {
                    try
                    {
                        var slice = await Task.Run(() => render.ExtractSlice(normalizedX, normalizedZ, angleYZ, angleXY), token);

                        if (!token.IsCancellationRequested && slice != null)
                        {
                            await this.InvokeAsync(async () =>
                            {
                                // If there's an existing image, dispose it
                                if (slicePreview.Image != null)
                                {
                                    var oldImage = slicePreview.Image;
                                    slicePreview.Image = null;
                                    oldImage.Dispose();
                                }

                                var rotatedSlice = RotateImage(slice);

                                // Calculate preview size
                                const float MIN_HEIGHT = 100f;
                                const int MIN_PREVIEW_SIZE = 300;
                                float scale = 1.0f;
                                int previewWidth = rotatedSlice.Width;
                                int previewHeight = rotatedSlice.Height;

                                if (rotatedSlice.Height < MIN_HEIGHT || rotatedSlice.Width < MIN_PREVIEW_SIZE)
                                {
                                    float scaleWidth = MIN_PREVIEW_SIZE / (float)rotatedSlice.Width;
                                    float scaleHeight = MIN_HEIGHT / (float)rotatedSlice.Height;
                                    scale = Math.Max(scaleWidth, scaleHeight);
                                    previewWidth = (int)(rotatedSlice.Width * scale);
                                    previewHeight = (int)(rotatedSlice.Height * scale);
                                }

                                slicePreview.Width = previewWidth + 10;
                                slicePreview.Height = previewHeight + 30;
                                slicePreview.Location = new Point(
                                    this.ClientSize.Width - slicePreview.Width - 10,
                                    10
                                );

                                slicePreview.Image = rotatedSlice;
                                slicePreview.Visible = true;

                                // Update resolution label
                                UpdateResolutionLabel(rotatedSlice.Width, rotatedSlice.Height);
                            });
                        }
                    }
                    catch (OperationCanceledException)
                    {
                        // Task was cancelled, ignore
                    }
                    catch (Exception ex)
                    {
                        await this.InvokeAsync(() =>
                        {
                            MessageBox.Show($"Error extracting slice: {ex.Message}");
                        });
                    }
                }, token);

                await _currentSliceTask;
            }
            catch (OperationCanceledException)
            {
                // Debounce was cancelled, ignore
            }
        }

        private async Task InvokeAsync(Action action)
        {
            if (this.InvokeRequired)
            {
                await Task.Run(() => this.Invoke(action));
            }
            else
            {
                action();
            }
        }

        private void UpdateResolutionLabel(int width, int height)
        {
            var resolutionLabel = this.Controls.OfType<Label>()
                .FirstOrDefault(l => l.Tag?.ToString() == "ResolutionLabel");

            if (resolutionLabel == null)
            {
                resolutionLabel = new Label
                {
                    AutoSize = true,
                    BackColor = Color.FromArgb(200, 0, 0, 0),
                    ForeColor = Color.White,
                    Padding = new Padding(5),
                    Tag = "ResolutionLabel"
                };
                this.Controls.Add(resolutionLabel);
            }

            resolutionLabel.Text = $"Resolution: {width} x {height}";
            resolutionLabel.Location = new Point(
                slicePreview.Left + 5,
                slicePreview.Bottom - resolutionLabel.Height - 5
            );
            resolutionLabel.BringToFront();
        }

        private async void RenderDicomForm_Load(object sender, EventArgs e)
        {
            Console.WriteLine("Loading 3D render...");
            ShowProgress(true);

            try
            {
                await Task.Run(() =>
                {
                    this.Invoke((MethodInvoker)delegate
                    {
                        InitializeOpenGL();
                        gl.Focus();
                    });

                    this.render = new Dicom3D(this.ddm, minSlice, maxSlice, carotidRect, UpdateProgress);

                    this.Invoke((MethodInvoker)delegate
                    {
                        InitializeShaders();
                        render.InitializeGL();
                        ShowProgress(false);
                        gl.Invalidate();
                        gl.Focus();
                    });
                    gl.Paint += GLControl_Paint;
                });
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error initializing 3D render: {ex.Message}");
            }
        }

        private void InitializeOpenGL()
        {
            gl.MakeCurrent();
            GL.ClearColor(Color.Black);
            GL.Enable(EnableCap.DepthTest);
            GL.Enable(EnableCap.Texture2D);
        }

        private void ShowProgress(bool visible)
        {
            progressBar.Visible = visible;
            progressLabel.Visible = visible;
            if (visible)
            {
                progressBar.Value = 0;
                progressBar.Maximum = 100;
            }
        }

        private void UpdateProgress(ProcessingProgress progress)
        {
            try
            {
                if (!IsDisposed && !Disposing)
                {
                    this.Invoke((MethodInvoker)delegate
                    {
                        if (!IsDisposed && !Disposing)
                        {
                            progressBar.Value = (int)progress.Percentage;
                            progressLabel.Text = $"{progress.CurrentStep} - {progress.CurrentValue} of {progress.TotalValue} slices ({progress.Percentage:F1}%)";
                        }
                    });
                }
            }
            catch (ObjectDisposedException)
            {
                // Ignore - form is being disposed
                Debug.WriteLine("Form disposed during progress update");
            }
            catch (InvalidOperationException)
            {
                // Ignore - form is being disposed
                Debug.WriteLine("Form disposed during progress update");
            }
        }

        #region Keyboard Controls

        private void RenderDicomForm_KeyDown(object sender, KeyEventArgs e)
        {
            pressedKeys.Add(e.KeyCode);
        }

        private void RenderDicomForm_KeyUp(object sender, KeyEventArgs e)
        {
            pressedKeys.Remove(e.KeyCode);
        }

        private void MoveTimer_Tick(object sender, EventArgs e)
        {
            bool moved = false;
            Vector3 viewDir = (cameraTarget - cameraPosition).Normalized();
            Vector3 right = Vector3.Cross(cameraUp, viewDir).Normalized();
            Vector3 up = Vector3.Cross(viewDir, right);

            // Déplacement avant/arrière (Z/S)
            if (pressedKeys.Contains(Keys.Z) || pressedKeys.Contains(Keys.W))
            {
                cameraPosition += viewDir * moveSpeed;
                cameraTarget += viewDir * moveSpeed;
                moved = true;
            }
            if (pressedKeys.Contains(Keys.S))
            {
                cameraPosition -= viewDir * moveSpeed;
                cameraTarget -= viewDir * moveSpeed;
                moved = true;
            }

            // Déplacement gauche/droite (Q/D)
            if (pressedKeys.Contains(Keys.Q) || pressedKeys.Contains(Keys.A))
            {
                cameraPosition += right * moveSpeed;
                cameraTarget += right * moveSpeed;
                moved = true;
            }
            if (pressedKeys.Contains(Keys.D))
            {
                cameraPosition -= right * moveSpeed;
                cameraTarget -= right * moveSpeed;
                moved = true;
            }

            // Déplacement haut/bas (E/C)
            if (pressedKeys.Contains(Keys.E))
            {
                cameraPosition += up * moveSpeed;
                cameraTarget += up * moveSpeed;
                moved = true;
            }
            if (pressedKeys.Contains(Keys.C))
            {
                cameraPosition -= up * moveSpeed;
                cameraTarget -= up * moveSpeed;
                moved = true;
            }

            // Reset position (R)
            if (pressedKeys.Contains(Keys.R))
            {
                ResetCamera();
                moved = true;
            }

            if (moved)
            {
                gl.Invalidate();
            }
        }

        private void ResetCamera()
        {
            cameraPosition = new Vector3(0, 0, 3f);
            cameraTarget = Vector3.Zero;
            cameraUp = Vector3.UnitY;
            rotationX = 0;
            rotationY = 0;
            zoom = 3.0f;
        }

        #endregion

        #region Mouse Controls

        private void GL_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                isMouseDown = true;
                lastMousePos = e.Location;
            }
        }

        private void GL_MouseUp(object sender, MouseEventArgs e)
        {
            isMouseDown = false;
        }

        private void GL_MouseMove(object sender, MouseEventArgs e)
        {
            if (!isMouseDown) return;

            float deltaX = -(e.X - lastMousePos.X) * 0.5f;
            float deltaY = (e.Y - lastMousePos.Y) * 0.5f;

            Vector3 viewDir = (cameraTarget - cameraPosition).Normalized();
            Vector3 right = Vector3.Cross(cameraUp, viewDir).Normalized();
            Vector3 up = Vector3.Cross(viewDir, right);

            Quaternion rotX = Quaternion.FromAxisAngle(up, MathHelper.DegreesToRadians(deltaX));
            Quaternion rotY = Quaternion.FromAxisAngle(right, MathHelper.DegreesToRadians(deltaY));
            Quaternion finalRotation = rotX * rotY;

            cameraPosition = Vector3.Transform(cameraPosition - cameraTarget, finalRotation) + cameraTarget;
            cameraUp = Vector3.Transform(cameraUp, finalRotation);

            // Debug angles
            viewDir = (cameraTarget - cameraPosition).Normalized();
            float angleX = MathHelper.RadiansToDegrees((float)Math.Atan2(viewDir.Y, Math.Sqrt(viewDir.X * viewDir.X + viewDir.Z * viewDir.Z)));
            float angleY = MathHelper.RadiansToDegrees((float)Math.Atan2(viewDir.X, viewDir.Z));
            float angleZ = MathHelper.RadiansToDegrees((float)Math.Atan2(cameraUp.X, cameraUp.Y));
            debugLabel.Text = $"X (Pitch): {angleX:F2}° | Y (Yaw): {angleY:F2}° | Z (Roll): {angleZ:F2}°";

            lastMousePos = e.Location;
            gl.Invalidate();
        }

        private void GL_MouseWheel(object sender, MouseEventArgs e)
        {
            float zoomFactor = 1.0f - (e.Delta * 0.001f);
            Vector3 zoomDir = cameraPosition - cameraTarget;
            cameraPosition = cameraTarget + zoomDir * zoomFactor;
            gl.Invalidate();
        }

        #endregion

        #region OpenGL Rendering

        private void InitializeShaders()
        {
            shaderProgram = CreateShaderProgram(vertexShaderSource, fragmentShaderSource);
            ColorShaderProgram = CreateShaderProgram(ColorVertexShader, ColorFragmentShader);
        }

        private int CreateShaderProgram(string vertexSource, string fragmentSource)
        {
            int vertexShader = GL.CreateShader(ShaderType.VertexShader);
            GL.ShaderSource(vertexShader, vertexSource);
            GL.CompileShader(vertexShader);

            int fragmentShader = GL.CreateShader(ShaderType.FragmentShader);
            GL.ShaderSource(fragmentShader, fragmentSource);
            GL.CompileShader(fragmentShader);

            int program = GL.CreateProgram();
            GL.AttachShader(program, vertexShader);
            GL.AttachShader(program, fragmentShader);
            GL.LinkProgram(program);

            GL.DeleteShader(vertexShader);
            GL.DeleteShader(fragmentShader);

            return program;
        }

        private void GLControl_Paint(object sender, PaintEventArgs e)
        {
            gl.MakeCurrent();
            GL.Clear(ClearBufferMask.ColorBufferBit | ClearBufferMask.DepthBufferBit);
            GL.UseProgram(shaderProgram);
            float aspect = (float)gl.ClientSize.Width / gl.ClientSize.Height;
            Matrix4 projection = Matrix4.CreatePerspectiveFieldOfView(MathHelper.PiOver4, aspect, 0.1f, 100f);
            Matrix4 view = Matrix4.LookAt(cameraPosition, cameraTarget, cameraUp);
            Matrix4 model = Matrix4.Identity;

            model *= Matrix4.CreateRotationX(MathHelper.DegreesToRadians(rotationX));
            model *= Matrix4.CreateRotationY(MathHelper.DegreesToRadians(rotationY));

            float scaleFactor = 1.0f;
            model *= Matrix4.CreateScale(scaleFactor);

            Vector3 centerOffset = new Vector3(0f, 0f, 0f);
            model *= Matrix4.CreateTranslation(centerOffset);

            int modelLoc = GL.GetUniformLocation(shaderProgram, "model");
            int viewLoc = GL.GetUniformLocation(shaderProgram, "view");
            int projLoc = GL.GetUniformLocation(shaderProgram, "projection");

            GL.UniformMatrix4(modelLoc, false, ref model);
            GL.UniformMatrix4(viewLoc, false, ref view);
            GL.UniformMatrix4(projLoc, false, ref projection);

            render.Render(shaderProgram, model, view, projection);

            DrawBoundingBox(model, view, projection);
            DrawSliceIndicator(model, view, projection);

            gl.SwapBuffers();
        }

        private void DrawBoundingBox(Matrix4 model, Matrix4 view, Matrix4 projection)
        {
            GL.UseProgram(ColorShaderProgram);

            GL.UniformMatrix4(GL.GetUniformLocation(ColorShaderProgram, "model"), false, ref model);
            GL.UniformMatrix4(GL.GetUniformLocation(ColorShaderProgram, "view"), false, ref view);
            GL.UniformMatrix4(GL.GetUniformLocation(ColorShaderProgram, "projection"), false, ref projection);
            GL.Uniform3(GL.GetUniformLocation(ColorShaderProgram, "color"), 1.0f, 0.0f, 0.0f); // Red color

            GL.Begin(PrimitiveType.Lines);

            // Bottom face
            GL.Vertex3(-0.5f, -0.5f, -0.5f); GL.Vertex3(0.5f, -0.5f, -0.5f);
            GL.Vertex3(0.5f, -0.5f, -0.5f); GL.Vertex3(0.5f, -0.5f, 0.5f);
            GL.Vertex3(0.5f, -0.5f, 0.5f); GL.Vertex3(-0.5f, -0.5f, 0.5f);
            GL.Vertex3(-0.5f, -0.5f, 0.5f); GL.Vertex3(-0.5f, -0.5f, -0.5f);

            // Top face
            GL.Vertex3(-0.5f, 0.5f, -0.5f); GL.Vertex3(0.5f, 0.5f, -0.5f);
            GL.Vertex3(0.5f, 0.5f, -0.5f); GL.Vertex3(0.5f, 0.5f, 0.5f);
            GL.Vertex3(0.5f, 0.5f, 0.5f); GL.Vertex3(-0.5f, 0.5f, 0.5f);
            GL.Vertex3(-0.5f, 0.5f, 0.5f); GL.Vertex3(-0.5f, 0.5f, -0.5f);

            // Vertical edges
            GL.Vertex3(-0.5f, -0.5f, -0.5f); GL.Vertex3(-0.5f, 0.5f, -0.5f);
            GL.Vertex3(0.5f, -0.5f, -0.5f); GL.Vertex3(0.5f, 0.5f, -0.5f);
            GL.Vertex3(0.5f, -0.5f, 0.5f); GL.Vertex3(0.5f, 0.5f, 0.5f);
            GL.Vertex3(-0.5f, -0.5f, 0.5f); GL.Vertex3(-0.5f, 0.5f, 0.5f);

            GL.End();
            GL.UseProgram(shaderProgram);
        }

        private void DrawSliceIndicator(Matrix4 model, Matrix4 view, Matrix4 projection)
        {
            if (!checkBox.Checked) return;

            GL.UseProgram(ColorShaderProgram);

            // Get normalized positions
            float normalizedX = ((float)slicePositionX.Value / (sliceWidth - 1)) - 0.5f;
            float normalizedZ = ((float)slicePositionZ.Value / (ddm.GetTotalSlices() - 1)) - 0.5f;

            float angleYZ = (float)((double)angleYZInput.Value * Math.PI / 180.0);
            float angleXY = (float)((double)angleXYInput.Value * Math.PI / 180.0);

            // Create rotations
            Quaternion rotationZ = Quaternion.FromAxisAngle(Vector3.UnitZ, angleXY);
            Quaternion rotationY = Quaternion.FromAxisAngle(Vector3.UnitY, angleYZ);
            Quaternion combinedRotation = rotationY * rotationZ;

            // Create matrices
            Matrix4 rotationMatrix = Matrix4.CreateFromQuaternion(combinedRotation);

            // Apply model transformation first, then rotation, then translation
            Matrix4 sliceModel = model * rotationMatrix * Matrix4.CreateTranslation(normalizedX, 0, normalizedZ);

            // Set uniforms
            GL.UniformMatrix4(GL.GetUniformLocation(ColorShaderProgram, "model"), false, ref sliceModel);
            GL.UniformMatrix4(GL.GetUniformLocation(ColorShaderProgram, "view"), false, ref view);
            GL.UniformMatrix4(GL.GetUniformLocation(ColorShaderProgram, "projection"), false, ref projection);

            // Set color to semi-transparent red
            GL.Enable(EnableCap.Blend);
            GL.BlendFunc(BlendingFactor.SrcAlpha, BlendingFactor.OneMinusSrcAlpha);
            GL.Uniform3(GL.GetUniformLocation(ColorShaderProgram, "color"), 1.0f, 0.0f, 0.0f);

            // Draw the slice plane
            GL.Begin(PrimitiveType.Quads);
            for (int i = 0; i < sliceIndicatorVertices.Length; i += 3)
            {
                GL.Vertex3(
                    sliceIndicatorVertices[i],
                    sliceIndicatorVertices[i + 1],
                    sliceIndicatorVertices[i + 2]
                );
            }
            GL.End();

            // Draw coordinate axes
            float axisLength = 0.2f;
            GL.LineWidth(2.0f);
            GL.Begin(PrimitiveType.Lines);

            // Normal vector - Red
            GL.Uniform3(GL.GetUniformLocation(ColorShaderProgram, "color"), 1.0f, 0.0f, 0.0f);
            GL.Vertex3(0, 0, 0);
            GL.Vertex3(axisLength, 0, 0);

            // Y axis - Green
            GL.Uniform3(GL.GetUniformLocation(ColorShaderProgram, "color"), 0.0f, 1.0f, 0.0f);
            GL.Vertex3(0, 0, 0);
            GL.Vertex3(0, axisLength, 0);

            // Z axis - Blue
            GL.Uniform3(GL.GetUniformLocation(ColorShaderProgram, "color"), 0.0f, 0.0f, 1.0f);
            GL.Vertex3(0, 0, 0);
            GL.Vertex3(0, 0, axisLength);

            GL.End();
            GL.LineWidth(1.0f);

            GL.Disable(EnableCap.Blend);
            GL.UseProgram(shaderProgram);
        }

        private void GLControl_Resize(object sender, EventArgs e)
        {
            if (gl == null) return;

            gl.MakeCurrent();
            GL.Viewport(0, 0, gl.ClientSize.Width, gl.ClientSize.Height);
        }
        #endregion

        #region SaveSlice

        private void InitializeSlicePreviewEvents()
        {
            slicePreview.ContextMenuStrip = new ContextMenuStrip();
            var saveMenuItem = new ToolStripMenuItem("Enregistrer la coupe");
            saveMenuItem.Click += SaveSlice_Click;
            slicePreview.ContextMenuStrip.Items.Add(saveMenuItem);
        }

        private void InitializeSlicePreview()
        {
            slicePreview = new PictureBox
            {
                SizeMode = PictureBoxSizeMode.Zoom,
                BorderStyle = BorderStyle.FixedSingle,
                Width = 512,
                Height = 512,
                Anchor = AnchorStyles.Top | AnchorStyles.Right,
                BackColor = Color.Black,
                Visible = false
            };

            // Positionner en haut à droite
            slicePreview.Location = new Point(
                this.ClientSize.Width - slicePreview.Width - 20,
                20
            );

            // Ajouter au formulaire et configurer les événements
            this.Controls.Add(slicePreview);
            InitializeSlicePreviewEvents();
            slicePreview.BringToFront();
        }

        private void SaveSlice_Click(object sender, EventArgs e)
        {
            if (slicePreview.Image == null) return;

            string layersDir = Path.Combine(patientDirectory, "calque");

            // Créer le dossier calque s'il n'existe pas
            if (!Directory.Exists(layersDir))
            {
                Directory.CreateDirectory(layersDir);
            }

            // Trouver le prochain numéro de sous-dossier disponible
            int layerNumber = 1;
            string layerSubDir;
            do
            {
                layerSubDir = Path.Combine(layersDir, $"calque#{layerNumber}");
                layerNumber++;
            } while (Directory.Exists(layerSubDir));

            // Créer le sous-dossier
            Directory.CreateDirectory(layerSubDir);

            // Générer le nom du fichier avec timestamp
            string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string filename = $"coupe_{timestamp}.png";
            string fullPath = Path.Combine(layerSubDir, filename);

            try
            {
                // Sauvegarder l'image
                slicePreview.Image.Save(fullPath, System.Drawing.Imaging.ImageFormat.Png);
                MessageBox.Show($"Coupe sauvegardée dans:\n{fullPath}", "Sauvegarde réussie",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Erreur lors de la sauvegarde: {ex.Message}", "Erreur",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        #endregion

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                Debug.WriteLine("Disposing RenderDicomForm...");

                // Cancel any pending operations
                if (_sliceUpdateCts != null)
                {
                    _sliceUpdateCts.Cancel();
                    _sliceUpdateCts.Dispose();
                    _sliceUpdateCts = null;
                }

                // Wait for any current slice task to complete
                if (_currentSliceTask != null)
                {
                    try
                    {
                        _currentSliceTask.Wait(TimeSpan.FromSeconds(1));
                    }
                    catch (Exception)
                    {
                        // Ignore any exceptions during cleanup
                    }
                    _currentSliceTask = null;
                }

                // Dispose timers
                if (moveTimer != null)
                {
                    moveTimer.Stop();
                    moveTimer.Dispose();
                    moveTimer = null;
                }

                // Dispose GL resources
                if (gl != null)
                {
                    // Make sure we have the current context before cleaning up GL resources
                    try
                    {
                        gl.MakeCurrent();

                        // Delete shader programs
                        if (shaderProgram != 0)
                        {
                            GL.DeleteProgram(shaderProgram);
                            shaderProgram = 0;
                        }
                        if (ColorShaderProgram != 0)
                        {
                            GL.DeleteProgram(ColorShaderProgram);
                            ColorShaderProgram = 0;
                        }

                        // Dispose render object
                        if (render != null)
                        {
                            render.Dispose();
                            render = null;
                        }
                    }
                    catch (Exception)
                    {
                        // Ignore GL context errors during cleanup
                    }
                    finally
                    {
                        gl.Dispose();
                        gl = null;
                    }
                }

                // Dispose preview image
                if (slicePreview != null && slicePreview.Image != null)
                {
                    slicePreview.Image.Dispose();
                    slicePreview.Image = null;
                }

                // Clear collections
                pressedKeys.Clear();

                // Dispose Windows Forms controls
                if (components != null)
                {
                    components.Dispose();
                    components = null;
                }

                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
            }

            base.Dispose(disposing);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            // Stop any ongoing operations
            if (_sliceUpdateCts != null)
            {
                _sliceUpdateCts.Cancel();
            }

            if (moveTimer != null)
            {
                moveTimer.Stop();
            }

            // Remove event handlers
            if (gl != null)
            {
                gl.Paint -= GLControl_Paint;
                gl.Resize -= GLControl_Resize;
                gl.MouseDown -= GL_MouseDown;
                gl.MouseUp -= GL_MouseUp;
                gl.MouseMove -= GL_MouseMove;
                gl.MouseWheel -= GL_MouseWheel;
            }

            base.OnFormClosing(e);
        }
    }
}