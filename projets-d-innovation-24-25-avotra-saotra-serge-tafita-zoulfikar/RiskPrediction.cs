using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms;

public class RiskPrediction : Form
{
    private TableLayoutPanel layoutMain;
    private TableLayoutPanel layoutLeft;
    private Panel layoutRight;
    private Button btnSubmit;
    private TextBox txtResult;

    private GroupBox gbxAnomalie;
    private GroupBox gbxOptions;

    private Label lblDateNaissance;
    private DateTimePicker dtpDateNaissance;
    private Label lblDateIntervention;
    private DateTimePicker dtpDateIntervention;

    private Label lblAgeCalcule;
    private TextBox txtAgeCalcule;
    private Label lblAgeArrondi;
    private TextBox txtAgeArrondi;

    private Label lblSexe;
    private ComboBox cboSexe;

    private Label lblTechnique;
    private RadioButton rdbTechniquePatch;
    private RadioButton rdbTechniqueEversion;


    private CheckBox chkShunt;
    private CheckBox chkArterio;
    private CheckBox chkReinter;

private TextBox txtAnomalieCarotide;

    private CheckBox[] optionCheckboxes;

    string modelPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "random_forest_model.onnx");
    private readonly ComplicationPredictor _predictor;

    public RiskPrediction()
    {
        InitializeComponent();
        _predictor = new ComplicationPredictor(modelPath);
    }

    private void InitializeComponent()
    {
        this.SuspendLayout();

        // === Form settings ===
        this.Size = new Size(1000, 600);
        this.MinimumSize = new Size(1000, 600);
        this.Text = "Données Intervention";
        this.StartPosition = FormStartPosition.CenterScreen;
        this.BackColor = Color.White;

        // === Main layout ===
        layoutMain = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            Padding = new Padding(15),
        };
        layoutMain.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 60));
        layoutMain.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 40));

        // === LEFT COLUMN (existing perfect layout) ===
        layoutLeft = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            AutoSize = true,
            AutoScroll = true,
            Padding = new Padding(0),
        };

        Label MakeLabel(string text) => new Label
        {
            Text = text,
            Dock = DockStyle.Top,
            Font = new Font("Segoe UI", 9.25f),
            Margin = new Padding(2, 0, 0, 2),
            AutoSize = true
        };

        TableLayoutPanel MakeRow(Control label, Control input)
        {
            var panel = new TableLayoutPanel
            {
                Dock = DockStyle.Top,
                ColumnCount = 1,
                AutoSize = true,
                Margin = new Padding(0, 0, 0, 3)
            };
            panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            panel.Controls.Add(label, 0, 0);
            panel.Controls.Add(input, 0, 1);
            return panel;
        }

        // === Dates ===
        var panelDates = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            ColumnCount = 2,
            AutoSize = true,
            Margin = new Padding(0, 0, 0, 3)
        };
        panelDates.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        panelDates.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));

        lblDateNaissance = MakeLabel("Date de naissance");
        dtpDateNaissance = new DateTimePicker { Dock = DockStyle.Top, Format = DateTimePickerFormat.Short, Margin = new Padding(0, 0, 5, 0) };

        lblDateIntervention = MakeLabel("Date d'intervention");
        dtpDateIntervention = new DateTimePicker { Dock = DockStyle.Top, Format = DateTimePickerFormat.Short, Margin = new Padding(5, 0, 0, 0) };

        panelDates.Controls.Add(MakeRow(lblDateNaissance, dtpDateNaissance), 0, 0);
        panelDates.Controls.Add(MakeRow(lblDateIntervention, dtpDateIntervention), 1, 0);
        layoutLeft.Controls.Add(panelDates);

        // === Ages ===
        var panelAges = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            ColumnCount = 2,
            AutoSize = true,
            Margin = new Padding(0, 0, 0, 3)
        };
        panelAges.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        panelAges.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));

        lblAgeCalcule = MakeLabel("Âge (calculé)");
        txtAgeCalcule = new TextBox { Dock = DockStyle.Top, ReadOnly = true, Margin = new Padding(0, 0, 5, 0) };

        lblAgeArrondi = MakeLabel("Âge (arrondi)");
        txtAgeArrondi = new TextBox { Dock = DockStyle.Top, Margin = new Padding(5, 0, 0, 0) };

        panelAges.Controls.Add(MakeRow(lblAgeCalcule, txtAgeCalcule), 0, 0);
        panelAges.Controls.Add(MakeRow(lblAgeArrondi, txtAgeArrondi), 1, 0);
        layoutLeft.Controls.Add(panelAges);

        // === Sexe ===
        lblSexe = MakeLabel("Sexe / genre");
        cboSexe = new ComboBox
        {
            Dock = DockStyle.Top,
            DropDownStyle = ComboBoxStyle.DropDownList
        };
        cboSexe.Items.AddRange(new object[] { "Femme", "Homme" });
        cboSexe.SelectedIndex = 0;
        layoutLeft.Controls.Add(MakeRow(lblSexe, cboSexe));

        // === Technique ===
        lblTechnique = MakeLabel("Technique chirurgicale");
        var radiosPanel = new FlowLayoutPanel
        {
            Dock = DockStyle.Top,
            FlowDirection = FlowDirection.LeftToRight,
            AutoSize = true
        };
        rdbTechniquePatch = new RadioButton { Text = "Patch", AutoSize = true };
        rdbTechniqueEversion = new RadioButton { Text = "Éversion", AutoSize = true };
        radiosPanel.Controls.Add(rdbTechniquePatch);
        radiosPanel.Controls.Add(rdbTechniqueEversion);
        layoutLeft.Controls.Add(MakeRow(lblTechnique, radiosPanel));

        // === Anomalie ===
        gbxAnomalie = new GroupBox
        {
            Text = "Anomalie de la carotide commune",
            Dock = DockStyle.Top,
            Font = new Font("Segoe UI", 9.25f),
            Padding = new Padding(8),
            Height = 55,
            Margin = new Padding(0, 3, 0, 3)
        };
        txtAnomalieCarotide = new TextBox { Dock = DockStyle.Fill };
        gbxAnomalie.Controls.Add(txtAnomalieCarotide);
        layoutLeft.Controls.Add(gbxAnomalie);

        //
        // === NEW: Section for required surgical features ===
        //
        var gbxFeatures = new GroupBox
        {
            Text = "Caractéristiques opératoires",
            Dock = DockStyle.Top,
            Font = new Font("Segoe UI", 9.25f),
            Padding = new Padding(8),
            AutoSize = true,
            Margin = new Padding(0, 3, 0, 3)
        };

        var flowFeatures = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            AutoSize = true,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false
        };

        // Separate, required checkboxes for model features
        chkShunt = new CheckBox { Text = "Shunt peropératoire", AutoSize = true };
        chkArterio = new CheckBox { Text = "Artériotomie effectuée", AutoSize = true };
        chkReinter = new CheckBox { Text = "Réintervention", AutoSize = true };

        flowFeatures.Controls.Add(chkShunt);
        flowFeatures.Controls.Add(chkArterio);
        flowFeatures.Controls.Add(chkReinter);
        gbxFeatures.Controls.Add(flowFeatures);

        // Add this group above the “Autres informations”
        layoutLeft.Controls.Add(gbxFeatures);

        // === Checkboxes ===
        gbxOptions = new GroupBox
        {
            Text = "Autres informations",
            Dock = DockStyle.Fill,
            Font = new Font("Segoe UI", 9.25f),
            Padding = new Padding(8),
            Margin = new Padding(0)
        };

        var flowOptions = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            AutoSize = true,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false
        };

        // Keep the remaining optional checkboxes
        optionCheckboxes = new[]
        {
            new CheckBox { Text = "Sténose significative", AutoSize = true },
            new CheckBox { Text = "Anomalie anatomique", AutoSize = true },
            new CheckBox { Text = "Complication neurologique / périphérique", AutoSize = true },
            new CheckBox { Text = "Antécédent AIT / AVC", AutoSize = true },
            new CheckBox { Text = "Complication cardiaque", AutoSize = true }
        };

        flowOptions.Controls.AddRange(optionCheckboxes);
        gbxOptions.Controls.Add(flowOptions);
        layoutLeft.Controls.Add(gbxOptions);

        // === RIGHT COLUMN ===
        layoutRight = new Panel
        {
            Dock = DockStyle.Fill,
            Padding = new Padding(10)
        };

        btnSubmit = new Button
        {
            Text = "Evaluer les risques",
            Dock = DockStyle.Top,
            Height = 40,
            BackColor = Color.FromArgb(70, 130, 180),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            Font = new Font("Segoe UI", 10, FontStyle.Bold)
        };

        txtResult = new TextBox
        {
            Dock = DockStyle.Fill,
            Multiline = true,
            ScrollBars = ScrollBars.Vertical,
            ReadOnly = true,
            Font = new Font("Consolas", 9),
            BackColor = Color.WhiteSmoke,
            BorderStyle = BorderStyle.FixedSingle,
            Margin = new Padding(0, 10, 0, 0)
        };

        layoutRight.Controls.Add(txtResult);
        layoutRight.Controls.Add(btnSubmit);

        layoutMain.Controls.Add(layoutLeft, 0, 0);
        layoutMain.Controls.Add(layoutRight, 1, 0);
        this.Controls.Add(layoutMain);

        this.ResumeLayout(false);

        // === Events ===
        dtpDateNaissance.ValueChanged += UpdateAgeFields;
        dtpDateIntervention.ValueChanged += UpdateAgeFields;
        btnSubmit.Click += OnSubmit;
    }


    private Label MakeLabel(string text)
    {
        return new Label
        {
            Text = text,
            Dock = DockStyle.Top,
            Font = new Font("Segoe UI", 9.25f),
            Margin = new Padding(2, 0, 0, 2),
            AutoSize = true
        };
    }

    private TableLayoutPanel MakeRow(Control label, Control input)
    {
        var panel = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            ColumnCount = 1,
            AutoSize = true,
            Margin = new Padding(0, 0, 0, 3)
        };
        panel.Controls.Add(label, 0, 0);
        panel.Controls.Add(input, 0, 1);
        return panel;
    }

    private void UpdateAgeFields(object? sender, EventArgs e)
    {
        try
        {
            var naissance = dtpDateNaissance.Value.Date;
            var intervention = dtpDateIntervention.Value.Date;

            if (intervention < naissance)
            {
                txtAgeCalcule.Text = "";
                txtAgeArrondi.Text = "";
                return;
            }

            var age = (intervention - naissance).TotalDays / 365.25;
            txtAgeCalcule.Text = age.ToString("0.00");
            txtAgeArrondi.Text = Math.Round(age).ToString();
        }
        catch
        {
            txtAgeCalcule.Text = "";
            txtAgeArrondi.Text = "";
        }
    }

    private void OnSubmit(object? sender, EventArgs e)
    {
        txtResult.ForeColor = Color.Black;
        txtResult.Text = "";

        // Validate required fields
        if (string.IsNullOrWhiteSpace(txtAgeArrondi.Text)
            || string.IsNullOrWhiteSpace(txtAgeCalcule.Text)
            || cboSexe.SelectedIndex < 0
            || (!rdbTechniquePatch.Checked && !rdbTechniqueEversion.Checked))
        {
            txtResult.ForeColor = Color.DarkRed;
            txtResult.Text = "❌ Erreur : Certains champs obligatoires sont vides ou non valides.";
            return;
        }

        // Determine genre (Femme=1, Homme=2)
        int genreValue = cboSexe.SelectedItem == "Femme" ? 1 : 2;

        // Determine technique (Patch=1, Eversion=2)
        int techniqueValue = rdbTechniquePatch.Checked ? 1 : 2;

        float shuntValue = chkShunt.Checked ? 1f : 0f;
        float arterioValue = chkArterio.Checked ? 1f : 0f;
        float reinterValue = chkReinter.Checked ? 1f : 0f;

        // Checkboxes combined value
        int checkboxesValue = optionCheckboxes.Any(c => c.Checked) ? 1 : 0;

        // Compile data
        string result =
            $@"Résumé des données soumises:

            Date de naissance : {dtpDateNaissance.Value:dd/MM/yyyy}
            Date d'intervention : {dtpDateIntervention.Value:dd/MM/yyyy}
            Âge calculé : {txtAgeCalcule.Text}
            Âge arrondi : {txtAgeArrondi.Text}
            Sexe : {genreValue}
            Technique : {techniqueValue}
            Anomalie carotide : {(string.IsNullOrWhiteSpace(txtAnomalieCarotide.Text) ? "(vide)" : txtAnomalieCarotide.Text)}
            Shunt: {(shuntValue == 1 ? "Oui" : "Non")},
            Arterio: {(arterioValue == 1 ? "Oui" : "Non")},
            Ré-intervention: {(reinterValue == 1 ? "Oui" : "Non")},
            Autres anomalies : {(checkboxesValue == 1 ? "Oui" : "Non")}";

        // Convert inputs to floats (same order as training)
        float[] features = {
            float.Parse(txtAgeCalcule.Text),
            float.Parse(txtAgeArrondi.Text),
            (float)genreValue,
            (float)(techniqueValue == 1 ? 1 : 0), // s_plus (example)
            (float)techniqueValue,
            shuntValue,
            arterioValue,
            reinterValue,
            string.IsNullOrWhiteSpace(txtAnomalieCarotide.Text) ? 0f : 1f, // anomalie
            (float)checkboxesValue, // anomalie_comm
        };

        // Predict complication
        var (prediction, probability) = _predictor.Predict(features);

        // Display result
        string verdict = prediction == 1
            ? $"Risque de complication détecté ({probability * 100:F1}%)"
            : $"Aucun risque significatif détecté ({probability * 100:F1}%)";

        txtResult.ForeColor = prediction == 1 ? Color.DarkOrange : Color.DarkGreen;
        txtResult.Text = result + Environment.NewLine + Environment.NewLine + verdict;
    }
}
